"""
Pairing with a PIN through BlueZ (D-Bus), for BMS units that ask for a short code
(for JK BMS it is usually 1234) on the first connection.

We register a temporary BlueZ "agent" that answers any PIN/passkey request with
the code you typed, call Device1.Pair() and unregister the agent again. Once the
device is paired (and trusted) BlueZ remembers it and this step is skipped.

NOTE: do not add `from __future__ import annotations` here - dbus_fast reads the
string annotations ("o", "s", "u" ...) as D-Bus type signatures.
"""
import asyncio
import logging

from dbus_fast import BusType, DBusError
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, method

log = logging.getLogger("jkmon.pair")

AGENT_PATH = "/org/jkmon/agent"
BLUEZ = "org.bluez"


class PairError(Exception):
    """Pairing failed for a reason the user should see (wrong PIN, device not found...)."""


class PinAgent(ServiceInterface):
    def __init__(self, pin: str):
        super().__init__("org.bluez.Agent1")
        self.pin = pin

    @method()
    def Release(self):
        pass

    @method()
    def RequestPinCode(self, device: "o") -> "s":  # noqa: F821
        log.info("BlueZ asked for a PIN code")
        return self.pin

    @method()
    def DisplayPinCode(self, device: "o", pincode: "s"):  # noqa: F821
        pass

    @method()
    def RequestPasskey(self, device: "o") -> "u":  # noqa: F821
        log.info("BlueZ asked for a passkey")
        return int(self.pin)

    @method()
    def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):  # noqa: F821
        pass

    @method()
    def RequestConfirmation(self, device: "o", passkey: "u"):  # noqa: F821
        pass  # returning without error = "yes"

    @method()
    def RequestAuthorization(self, device: "o"):  # noqa: F821
        pass

    @method()
    def AuthorizeService(self, device: "o", uuid: "s"):  # noqa: F821
        pass

    @method()
    def Cancel(self):
        pass


def _device_path(address: str, adapter: str) -> str:
    return f"/org/bluez/{adapter}/dev_" + address.upper().replace(":", "_")


async def ensure_paired(address: str, pin: str, adapter: str = "hci0", timeout: float = 40.0) -> bool:
    """Pair with `address` using `pin`. Returns True if pairing was done now,
    False if the device was already paired. Raises PairError on failure."""
    path = _device_path(address, adapter)
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    registered = False
    mgr = None
    try:
        try:
            intro = await bus.introspect(BLUEZ, path)
        except Exception as e:  # device object is gone from BlueZ (not seen recently)
            raise PairError(f"BlueZ does not see the device {address}: {e}") from e
        dev = bus.get_proxy_object(BLUEZ, path, intro).get_interface("org.bluez.Device1")

        if await dev.get_paired():
            log.info("%s is already paired", address)
            return False

        agent = PinAgent(pin)
        bus.export(AGENT_PATH, agent)
        mgr_intro = await bus.introspect(BLUEZ, "/org/bluez")
        mgr = bus.get_proxy_object(BLUEZ, "/org/bluez", mgr_intro).get_interface("org.bluez.AgentManager1")
        await mgr.call_register_agent(AGENT_PATH, "KeyboardOnly")
        registered = True
        await mgr.call_request_default_agent(AGENT_PATH)

        log.info("pairing with %s ...", address)
        try:
            await asyncio.wait_for(dev.call_pair(), timeout)
        except asyncio.TimeoutError as e:
            raise PairError("The BMS did not answer the pairing request within 40 s") from e
        except DBusError as e:
            if e.type == "org.bluez.Error.AlreadyExists":
                log.info("already paired")
            elif e.type.startswith("org.bluez.Error.Authentication"):
                raise PairError(f"The BMS rejected the PIN {pin!r} ({e.type.rsplit('.', 1)[-1]})") from e
            else:
                raise PairError(f"{e.type}: {e.text}") from e

        try:
            await dev.set_trusted(True)
        except Exception:  # not critical
            log.debug("could not set Trusted", exc_info=True)
        log.info("paired with %s", address)
        return True
    finally:
        if registered and mgr is not None:
            try:
                await mgr.call_unregister_agent(AGENT_PATH)
            except Exception:
                pass
        bus.disconnect()
