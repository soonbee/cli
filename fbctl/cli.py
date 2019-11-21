from fbctl import utils
from fbctl.log import logger
from fbctl.rediscli import (
    RedisCliCluster,
    RedisCliConfig,
    RedisCliInfo,
    RedisCliUtil
)


# pylint: disable=redefined-builtin
# need to parameter all for cli options
def _command(sub_cmd, all, host, port):
    if all:
        RedisCliUtil.command_all(sub_cmd=sub_cmd, formatter=utils.print_table)
    else:
        RedisCliUtil.command(sub_cmd=sub_cmd, host=host, port=port)


def ping(all=False, host=None, port=0):
    """Send ping command

    :param all: If true, send command to all
    :param host: host info
    :param port: port info
    """
    if not isinstance(all, bool):
        logger.error("option '--all' can use only 'True' or 'False'")
        return
    sub_cmd = 'ping'
    _command(sub_cmd, all, host, port)


def reset_oom(all=False, host=None, port=0):
    """Send reset oom command

    :param all: If true, send command to all
    :param host: host info
    :param port: port info
    """
    if not isinstance(all, bool):
        logger.error("option '--all' can use only 'True' or 'False'")
        return
    sub_cmd = 'resetOom'
    _command(sub_cmd, all, host, port)


def reset_info(key, all=False, host=None, port=0):
    """Send reset info

    :param key: resetting target key string
    :param all: If true, send command to all
    :param host: host info
    :param port: port info
    """
    if not isinstance(all, bool):
        logger.error("option '--all' can use only 'True' or 'False'")
        return
    sub_cmd = 'resetInfo %s' % key
    _command(sub_cmd, all, host, port)


def metakeys(key, all=False, host=None, port=0):
    """Get metakeys

    :param key: resetting target key string
    :param all: If true, send command to all
    :param host: host info
    :param port: port info
    """
    if not isinstance(all, bool):
        logger.error("option '--all' can use only 'True' or 'False'")
        return
    sub_cmd = 'metakeys "%s"' % key
    _command(sub_cmd, all, host, port)


class Cli(object):
    """This is Cli command (redis-cli wrapper)

    You can check redis and cluster info.

    """

    def __init__(self):
        self.info = RedisCliInfo()
        self.config = RedisCliConfig()
        self.cluster = RedisCliCluster()
        self.ping = ping
        self.reset_oom = reset_oom
        self.reset_info = reset_info
        self.metakeys = metakeys
