import os
from functools import reduce
import time

from ltcli import color
from ltcli import config
from ltcli import cluster_util
from ltcli.center import Center
from ltcli.log import logger
from ltcli.rediscli_util import RedisCliUtil
from ltcli.redistrib2.custom_trib import rebalance_cluster_cmd
from ltcli.exceptions import (
    ClusterIdError,
    ClusterNotExistError,
    LightningDBError,
    ClusterRedisError
)


def _change_cluster(cluster_id):
    if not isinstance(cluster_id, int):
        raise ClusterIdError(cluster_id)
    root_of_cli_config = config.get_root_of_cli_config()
    head_path = os.path.join(root_of_cli_config, 'HEAD')
    cluster_list = cluster_util.get_cluster_list()
    if cluster_id not in cluster_list + [-1]:
        raise ClusterNotExistError(cluster_id)
    with open(head_path, 'w') as fd:
        fd.write('%s' % cluster_id)


class Cluster(object):
    """This is cluster command
    """

    def __init__(self, print_mode='screen'):
        self._print_mode = print_mode

    def stop(self, force=False, master=True, slave=True):
        """Stop cluster
        """
        if not isinstance(force, bool):
            logger.error("option '--force' can use only 'True' or 'False'")
            return
        if not isinstance(master, bool):
            logger.error("option '--master' can use only 'True' or 'False'")
            return
        if not isinstance(slave, bool):
            logger.error("option '--slave' can use only 'True' or 'False'")
            return
        center = Center()
        center.update_ip_port()
        success = center.check_hosts_connection()
        if not success:
            return
        center.stop_redis(force, master=master, slave=slave)

    def start(self, profile=False, master=True, slave=True):
        """Start cluster
        """
        logger.debug("command 'cluster start'")
        if not isinstance(profile, bool):
            logger.error("option '--profile' can use only 'True' or 'False'")
            return
        if not isinstance(master, bool):
            logger.error("option '--master' can use only 'True' or 'False'")
            return
        if not isinstance(slave, bool):
            logger.error("option '--slave' can use only 'True' or 'False'")
            return
        center = Center()
        center.update_ip_port()
        success = center.check_hosts_connection()
        if not success:
            return
        center.ensure_cluster_exist()
        if master:
            master_alive_count = center.get_alive_master_redis_count()
            if master_alive_count > 0:
                msg = [
                    'Fail to start master nodes... ',
                    'Must be checked running master processes!\n',
                    'We estimate that ',
                    "redis 'MASTER' processes is {}".format(master_alive_count)
                ]
                raise LightningDBError(11, ''.join(msg))
        slave_alive_count = center.get_alive_slave_redis_count()
        if slave:
            if slave_alive_count > 0:
                msg = [
                    'Fail to start slave nodes... ',
                    'Must be checked running slave processes!\n',
                    'We estimate that ',
                    "redis 'SLAVE' processes is {}".format(slave_alive_count)
                ]
                raise LightningDBError(12, ''.join(msg))
        center.backup_server_logs(master=master, slave=slave)
        center.create_redis_data_directory()

        # equal to cluster.configure()
        center.configure_redis()
        center.sync_conf(show_result=True)

        center.start_redis_process(profile, master=master, slave=slave)
        center.wait_until_all_redis_process_up(master=master, slave=slave)

    def create(self, yes=False):
        """Create cluster

        Before create cluster, all redis should be started.
        """
        center = Center()
        center.update_ip_port()
        success = center.check_hosts_connection()
        if not success:
            return

        m_count = len(center.master_host_list) * len(center.master_port_list)
        if m_count < 3:
            msg = [
                'To create cluster, ',
                '3 master processes should be included at least.',
            ]
            raise ClusterRedisError(''.join(msg))

        # if need to cluster start
        alive_count = center.get_alive_all_redis_count()
        my_alive_count = center.get_alive_all_redis_count(check_owner=True)
        if alive_count != my_alive_count:
            raise ClusterRedisError('The port range is already taken.')
        all_count = len(center.all_host_list)
        if alive_count < all_count:
            logger.debug('cluster start in create')
            # init
            center.backup_server_logs()
            center.create_redis_data_directory()

            # cluster configure
            center.configure_redis()
            center.sync_conf(show_result=True)

            # cluster start
            center.start_redis_process()
            center.wait_until_all_redis_process_up()

        key = 'cluster-node-timeout'
        m_hosts = center.master_host_list
        m_ports = center.master_port_list
        origin_m_value = center.cli_config_get(key, m_hosts[0], m_ports[0])
        if not origin_m_value:
            msg = "RedisConfigKeyError(master): '{}'".format(key)
            logger.warning(msg)
        s_hosts = center.slave_host_list
        s_ports = center.slave_port_list
        if s_hosts and s_ports:
            origin_s_value = center.cli_config_get(key, s_hosts[0], s_ports[0])
            if not origin_s_value:
                msg = "RedisConfigKeyError(slave): '{}'".format(key)
                logger.warning(msg)
        if origin_m_value:
            # cli config set cluster-node-timeout 2000
            logger.debug('set cluster node time out 2000 for create')
            center.cli_config_set_all(key, '2000', m_hosts, m_ports)
            if s_hosts and s_ports and origin_s_value:
                center.cli_config_set_all(key, '2000', s_hosts, s_ports)
        center.create_cluster(yes)
        if origin_m_value:
            # cli config restore cluster-node-timeout
            logger.debug('restore cluster node time out')
            center.cli_config_set_all(key, origin_m_value, m_hosts, m_ports)
            if s_hosts and s_ports and origin_s_value:
                v = origin_s_value
                center.cli_config_set_all(key, v, s_hosts, s_ports)

    def clean(self, logs=False):
        """Clean cluster
        """
        if not isinstance(logs, bool):
            logger.error("option '--logs' can use only 'True' or 'False'")
            return
        center = Center()
        center.update_ip_port()
        if logs:
            center.remove_all_of_redis_log_force()
            return
        center.cluster_clean()

    def use(self, cluster_id):
        """Change selected cluster

        :param cluster_id: target cluster #
        """
        _change_cluster(cluster_id)
        cluster_id = '-' if cluster_id == -1 else cluster_id
        logger.info("Cluster '{}' selected.".format(cluster_id))

    def ls(self):
        """Check cluster list"""
        logger.info(cluster_util.get_cluster_list())

    def restart(
        self,
        force_stop=False,
        reset=False,
        cluster=False,
        profile=False,
        yes=False,
    ):
        """Restart redist cluster
        :param force: If true, send SIGKILL. If not, send SIGINT
        :param reset: If true, clean(rm data).
        """
        if not isinstance(force_stop, bool):
            msg = [
                "option '--force-stop' can use only ",
                "'True' or 'False'",
            ]
            logger.error(''.join(msg))
            return
        if not isinstance(reset, bool):
            logger.error("option '--reset' can use only 'True' or 'False'")
            return
        if not isinstance(cluster, bool):
            logger.error("option '--cluster' can use only 'True' or 'False'")
            return
        if not reset and cluster:
            msg = "option '--cluster' can used only with option '--reset'"
            logger.error(msg)
            return
        if not cluster and yes:
            msg = "option '--yes' can used only with option '--cluster'"
            logger.error(msg)
            return
        center = Center()
        center.update_ip_port()
        success = center.check_hosts_connection()
        if not success:
            return
        center.stop_redis(force=force_stop)
        if reset:
            self.clean()
        self.start(profile=profile)
        if cluster:
            self.create(yes=yes)

    def configure(self):
        center = Center()
        center.update_ip_port()
        success = center.check_hosts_connection()
        if not success:
            return
        center.configure_redis()
        center.sync_conf(show_result=True)

    def rowcount(self):
        """Query and show cluster row count"""
        logger.debug('rowcount')
        # open-redis-cli-all info Tablespace | grep totalRows | awk -F ',
        # ' '{print $4}' | awk -F '=' '{sum += $2} END {print sum}'
        host_list = config.get_master_host_list()
        port_list = config.get_master_port_list()
        outs, _ = RedisCliUtil.command_raw_all(
            'info Tablespace', host_list, port_list)
        lines = outs.splitlines()
        key = 'totalRows'
        filtered_lines = (filter(lambda x: key in x, lines))
        ld = RedisCliUtil.to_list_of_dict(filtered_lines)
        # row_count = reduce(lambda x, y: {key: int(x[key]) + int(y[key])}, ld)
        row_count = reduce(lambda x, y: x + int(y[key]), ld, 0)
        self._print(row_count)

    def rebalance(self, ip, port):
        """Rebalance

        :param ip: rebalance target ip
        :param port: rebalance target port
        """
        rebalance_cluster_cmd(ip, port)

    def add_slave(self, yes=False):
        """Add slaves to cluster additionally
        """
        logger.debug('add_slave')
        if not isinstance(yes, bool):
            logger.error("option '--yes' can use only 'True' or 'False'")
            return
        center = Center()
        center.update_ip_port()
        # check
        s_hosts = center.slave_host_list
        s_ports = center.slave_port_list
        if not s_hosts:
            raise ClusterRedisError('Slave host cannot empty')
        if not s_ports:
            raise ClusterRedisError('Slave port cannot empty')
        success = center.check_hosts_connection(hosts=s_hosts)
        if not success:
            return
        center.ensure_cluster_exist()
        slave_alive_count = center.get_alive_slave_redis_count()
        if slave_alive_count > 0:
            msg = [
                'Fail to start slave nodes... ',
                'Must be checked running slave processes!\n',
                'We estimate that ',
                "redis 'SLAVE' processes is {}".format(slave_alive_count)
            ]
            raise LightningDBError(12, ''.join(msg))

        # confirm info
        result = center.confirm_node_port_info(skip=yes)
        if not result:
            logger.warn('Cancel add-slave')
            return
        # clean
        center.cluster_clean(master=False)
        # backup logs
        center.backup_server_logs(master=False)
        center.create_redis_data_directory(master=False)
        # configure
        center.configure_redis(master=False)
        center.sync_conf()
        # start
        center.start_redis_process(master=False)
        center.wait_until_all_redis_process_up()

        # change redis config temporarily
        key = 'cluster-node-timeout'
        origin_s_value = center.cli_config_get(key, s_hosts[0], s_ports[0])
        if not origin_s_value:
            msg = "RedisConfigKeyError: '{}'".format(key)
            logger.warning(msg)
        if origin_s_value:
            # cli config set cluster-node-timeout 2000
            logger.debug('set cluster node time out 2000 for create')
            center.cli_config_set_all(key, '2000', s_hosts, s_ports)
        # create
        center.replicate()
        if origin_s_value:
            # cli config restore cluster-node-timeout
            logger.debug('restore cluster node time out')
            center.cli_config_set_all(key, origin_s_value, s_hosts, s_ports)

    def failover(self):
        """Replace disconnected master with slave.

        Replace disconnected master with slave.
        If disconnected master comes back to live, it become slave.
        """
        center = Center()
        center.update_ip_port()
        master_obj_list = center.get_master_obj_list()
        msg = color.yellow('{} has no alive slave to proceed failover')
        all_alive = True
        for node in master_obj_list:
            if node['status'] != 'connected':
                all_alive = False
                success = False
                for slave in node['slaves']:
                    if slave['status'] == 'connected':
                        logger.info('failover {} for {}'.format(
                            slave['addr'],
                            node['addr']
                        ))
                        stdout = center.run_failover(
                            slave['addr'],
                            take_over=True
                        )
                        if stdout != 'OK':
                            continue
                        logger.info('OK')
                        success = True
                        break
                if not success:
                    logger.info(msg.format(node['addr']))
        if all_alive:
            logger.info('All master is alive')

    def failback(self):
        center = Center()
        center.update_ip_port()
        master_obj_list = center.get_master_obj_list()
        disconnected_list = []
        paused_list = []
        for master in master_obj_list:
            if master['status'] == 'disconnected':
                disconnected_list.append(master['addr'])
            if master['status'] == 'paused':
                paused_list.append(master['addr'])
            for slave in master['slaves']:
                if slave['status'] == 'disconnected':
                    disconnected_list.append(slave['addr'])
                if slave['status'] == 'paused':
                    paused_list.append(slave['addr'])
        classified_disconnected_list = {}
        classified_paused_list = {}
        for disconnected in disconnected_list:
            host, port = disconnected.split(':')
            if host not in classified_disconnected_list:
                classified_disconnected_list[host] = []
            classified_disconnected_list[host].append(port)
        for paused in paused_list:
            host, port = paused.split(':')
            if host not in classified_paused_list:
                classified_paused_list[host] = []
            classified_paused_list[host].append(port)
        current_time = time.strftime("%Y%m%d-%H%M", time.gmtime())
        for host, ports in classified_disconnected_list.items():
            logger.info('run {}:{}'.format(host, '|'.join(ports)))
            center.run_redis_process(host, ports, False, current_time)
        for host, ports in classified_paused_list.items():
            logger.info('restart {}:{}'.format(host, '|'.join(ports)))
            center.stop_redis_process(host, ports)
            center.run_redis_process(host, ports, False, current_time)
        if not classified_disconnected_list and not classified_paused_list:
            logger.info('All redis is alive')

    def tree(self):
        """The results of 'cli cluster nodes' are displayed in tree format.
        """
        center = Center()
        center.update_ip_port()
        master_node_list = center.get_master_obj_list()
        output_msg = []
        for master_node in master_node_list:
            addr = master_node['addr']
            status = master_node['status']
            msg = '{}({})'.format(addr, status)
            if status == 'disconnected':
                msg = color.red(msg)
            if status == 'paused':
                msg = color.yellow(msg)
            output_msg.append(msg)
            for slave_node in master_node['slaves']:
                addr = slave_node['addr']
                status = slave_node['status']
                msg = '{}({})'.format(addr, status)
                if status == 'disconnected':
                    msg = color.red(msg)
                if status == 'paused':
                    msg = color.yellow(msg)
                output_msg.append('|__ ' + msg)
            output_msg.append('')
        logger.info(color.ENDC + '\n'.join(output_msg))

    def _print(self, text):
        if self._print_mode == 'screen':
            logger.info(text)
