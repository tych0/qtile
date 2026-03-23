import socket
from subprocess import DEVNULL, run

from libqtile.log_utils import logger
from libqtile.widget import base


class NetUP(base.BackgroundPoll):
    """
    A widget to display whether the network connection is up or down by probing a host via ping
    or tcp connection.

    By default ``host`` parameter is set to ``None``.
    """

    defaults = [
        ("host", None, "Host to probe."),
        ("method", "ping", "tcp or ping."),
        ("port", 443, "TCP port."),
        ("update_interval", 30, "Update interval in seconds."),
        ("display_fmt", "NET {0}", "Display format."),
        ("up_foreground", "FFFFFF", "Font color when host is up."),
        ("down_foreground", "FF0000", "Font color when host is down."),
        ("up_string", "up", "String to display when host is up."),
        ("down_string", "down", "String to display when host is down."),
    ]

    def __init__(self, **config):
        base.BackgroundPoll.__init__(self, **config)
        self.add_defaults(NetUP.defaults)

    def is_host_empty(self):
        if not self.host:
            logger.error("Host is not set")
            return False
        return True

    def validate_method(self):
        if self.method in ("ping", "tcp"):
            return True
        logger.error("Method is invalid")
        return False

    def validate_port(self):
        if not isinstance(self.port, int):
            logger.error("Port is invalid")
            return False
        if 1 <= self.port <= 65535:
            return True
        logger.error("Port is invalid")
        return False

    def check_ping(self):
        process = run(["ping", "-c", "1", self.host], stdout=DEVNULL, stderr=DEVNULL)
        return process.returncode

    def check_tcp(self):
        sc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sc.settimeout(1)
        try:
            returncode = sc.connect_ex((self.host, self.port))
        except OSError:
            returncode = -1
        finally:
            sc.close()
        return returncode

    def is_up(self):
        if self.method == "ping":
            return self.check_ping() == 0
        if self.method == "tcp":
            return self.check_tcp() == 0

    def poll(self):
        if (
            not self.is_host_empty()
            or not self.validate_method()
            or (self.method == "tcp" and not self.validate_port())
        ):
            return "N/A"

        if self.is_up():
            self.layout.colour = self.up_foreground
            return self.display_fmt.format(self.up_string)
        self.layout.colour = self.down_foreground
        return self.display_fmt.format(self.down_string)
