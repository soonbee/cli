import time
import os
from threading import Thread
import socket
import subprocess
import shutil

from terminaltables import AsciiTable

from fbctl import config
from fbctl.log import logger
from fbctl import net
from fbctl.rediscli_util import RedisCliUtil
from fbctl.redistrib2 import command as trib
from fbctl import utils
from fbctl.deploy_util import DeployUtil, DEPLOYED
from fbctl import ask_util
from fbctl import color
from fbctl.exceptions import (
    SSHConnectionError,
    HostConnectionError,
    HostNameError,
    FileNotExistError,
    ClusterRedisError,
    ClusterNotExistError,
)


def get_ps_list_command(port_list):
    port_filter = '|'.join(str(x) for x in port_list)
    command = [
        "ps -ef",
        "grep 'redis-server'",
        "egrep '({})'".format(port_filter),
        "grep -v 'ps -ef'",
        "grep -v 'grep'",
    ]
    command = ' | '.join(command)
    return command


def get_my_ps_list_command(port_list, cluster_id):
    port_filter = '|'.join(str(x) for x in port_list)
    command = [
        "ps -ef",
        "grep 'redis-server'",
        "grep `whoami`",
        "grep cluster_{}".format(cluster_id),
        "egrep '({})'".format(port_filter),
        "grep -v 'ps -ef'",
        "grep -v 'grep'",
    ]
    command = ' | '.join(command)
    return command


class Center(object):
    def __init__(self):
        self.master_host_list = []
        self.slave_host_list = []
        self.master_port_list = []
        self.slave_port_list = []
        self.all_host_list = []

    def sync_conf(self, show_result=False):
        logger.info('sync conf')
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        conf_path = path_of_fb['conf_path']
        my_address = config.get_local_ip_list()
        meta = [['HOST', 'STATUS']]
        no_cluster_flag = False
        for host in self.all_host_list:
            client = net.get_ssh(host)
            cluster_path = path_of_fb['cluster_path']
            if not net.is_dir(client, cluster_path):
                no_cluster_flag = True
                meta.append([host, color.red('NO CLUSTER')])
                continue
            client.close()
            meta.append([host, color.green('OK')])
        if no_cluster_flag:
            utils.print_table(meta)
            logger.error('Cancel sync conf')
            return False
        meta = [['HOST', 'STATUS']]
        error_flag = False
        for host in self.all_host_list:
            if net.get_ip(host) in my_address:
                meta.append([host, color.green('OK')])
                continue
            client = net.get_ssh(host)
            try:
                net.copy_dir_to_remote(client, conf_path, conf_path)
                meta.append([host, color.green('OK')])
            except BaseException as ex:
                logger.debug(ex)
                meta.append([host, color.red('FAIL')])
                error_flag = True
            finally:
                client.close()
        if error_flag or show_result:
            utils.print_table(meta)
        if error_flag:
            logger.error('Fail conf sync')
            return False
        logger.info('OK')
        return True

    def sync_file(self, file_path, show_result=False):
        logger.info('sync conf')
        meta = [['HOST', 'STATUS']]
        my_address = config.get_local_ip_list()
        error_flag = False
        for host in self.all_host_list:
            client = net.get_ssh(host)
            sftp = net.get_sftp(client)
            if net.get_ip(host) in my_address:
                meta.append([host, color.green('OK')])
                continue
            try:
                sftp.put(file_path, file_path)
                meta.append([host, color.green('OK')])
            except Exception as ex:
                logger.debug(ex)
                meta.append([host, color.red('FAIL')])
                error_flag = True
            finally:
                sftp.close()
                client.close()
        if error_flag or show_result:
            utils.print_table(meta)
        if error_flag:
            logger.error('Fail file sync')
            return False
        logger.info('OK')
        return True

    def configure_redis(self, master=True, slave=True):
        logger.debug('configure redis')
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        sr2_redis_conf_temp = path_of_fb['sr2_redis_conf_temp']
        if os.path.exists(sr2_redis_conf_temp):
            shutil.rmtree(sr2_redis_conf_temp)
        os.mkdir(sr2_redis_conf_temp)
        sr2_redis_conf = path_of_fb['sr2_redis_conf']
        if not os.path.exists(sr2_redis_conf):
            os.mkdir(sr2_redis_conf)
        props_path = path_of_fb['redis_properties']
        prefix_srd = config.get_props(props_path, 'sr2_redis_data')
        prefix_sfdp = config.get_props(props_path, 'sr2_flash_db_path')
        ssd_count = config.get_props(props_path, 'ssd_count')
        sr2_redis_conf_temp = path_of_fb['sr2_redis_conf_temp']
        conf_path = path_of_fb['conf_path']
        user = os.environ['USER']
        command = []
        count = 0
        if master:
            template = 'redis-master.conf.template'
            template_path = os.path.join(conf_path, template)
            for port in self.master_port_list:
                # depence: [Errno 7] Argument list too long
                if count > 200:
                    command = ' '.join(command)
                    subprocess.check_output(command, shell=True)
                    logger.debug('subprocess: {}'.format(command))
                    command = []
                    count = 0
                count += 1
                ssd_no = config.get_sata_ssd_no(port, ssd_count)
                sr2_redis_data = '{}{}/{}'.format(prefix_srd, ssd_no, user)
                sr2_flash_db_path = '{}{}/{}/db/db-{}'.format(
                    prefix_sfdp,
                    ssd_no,
                    user,
                    port
                )
                file_name = 'redis-{}.conf'.format(port)
                export_envs = ' '.join([
                    'export SR2_REDIS_PORT={}'.format(port),
                    'export SR2_REDIS_DATA={}'.format(sr2_redis_data),
                    'export SR2_FLASH_DB_PATH={}'.format(sr2_flash_db_path),
                ])
                target = os.path.join(sr2_redis_conf_temp, file_name)
                command.append('{}; cat {} | envsubst > {};'.format(
                    export_envs,
                    template_path,
                    target,
                ))
        if slave and self.slave_port_list:
            template = 'redis-slave.conf.template'
            template_path = os.path.join(conf_path, template)
            for port in self.slave_port_list:
                # depence: [Errno 7] Argument list too long
                if count > 200:
                    command = ' '.join(command)
                    subprocess.check_output(command, shell=True)
                    logger.debug('subprocess: {}'.format(command))
                    command = []
                    count = 0
                count += 1
                ssd_no = config.get_sata_ssd_no(port, ssd_count)
                sr2_redis_data = '{}{}/{}'.format(prefix_srd, ssd_no, user)
                sr2_flash_db_path = '{}{}/{}/db/db-{}'.format(
                    prefix_sfdp,
                    ssd_no,
                    user,
                    port
                )
                file_name = 'redis-{}.conf'.format(port)
                export_envs = ' '.join([
                    'export SR2_REDIS_PORT={}'.format(port),
                    'export SR2_REDIS_DATA={}'.format(sr2_redis_data),
                    'export SR2_FLASH_DB_PATH={}'.format(sr2_flash_db_path),
                ])
                target = os.path.join(sr2_redis_conf_temp, file_name)
                command.append('{}; cat {} | envsubst > {};'.format(
                    export_envs,
                    template_path,
                    target,
                ))
        command = ' '.join(command)
        subprocess.check_output(command, shell=True)
        logger.debug('subprocess: {}'.format(command))
        command = 'find {} -type f | xargs -i cp "{{}}" {}'.format(
            sr2_redis_conf_temp,
            sr2_redis_conf
        )
        subprocess.check_output(command, shell=True)
        logger.debug('subprocess: {}'.format(command))

    def backup_server_logs(self, master=True, slave=True):
        """ Backup server logs

        Move redis log files to $SR2_REDIS_LOG/backup/<time-stamp>
        """
        logger.debug('backup_server_logs')
        current_time = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        sr2_redis_log = path_of_fb['sr2_redis_log']
        backup_path = os.path.join(sr2_redis_log, 'backup', current_time)
        logger.debug('backup path: {}'.format(backup_path))
        if master:
            logger.info('Backup redis master log in each MASTER hosts...')
            self._backup_server_logs(
                self.master_host_list,
                self.master_port_list,
                backup_path
            )
        if slave and self.slave_host_list:
            logger.info('Backup redis slave log in each SLAVE hosts...')
            self._backup_server_logs(
                self.slave_host_list,
                self.slave_port_list,
                backup_path
            )

    def _backup_server_logs(self, hosts, ports, backup_path):
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        sr2_redis_log = path_of_fb['sr2_redis_log']
        for host in hosts:
            logger.info(' - {}'.format(host))
            command = ['mkdir -p {};'.format(backup_path)]
            count = 0
            for port in ports:
                # depence: [Errno 7] Argument list too long
                if count > 100:
                    command = ' '.join(command)
                    client = net.get_ssh(host)
                    net.ssh_execute(client, command, allow_status=[0, 1])
                    client.close()
                    command = []
                    count = 0
                count += 1
                command.append('mv {0}/*{1}.log {2} &> /dev/null'.format(
                    sr2_redis_log,
                    port,
                    backup_path
                ))
            command = ' '.join(command)
            client = net.get_ssh(host)
            net.ssh_execute(client, command, allow_status=[0, 1])
            client.close()

    def conf_backup(self, host, cluster_id, tag):
        logger.info('Backup conf of cluster {}...'.format(cluster_id))
        # prepare
        path_of_fb = config.get_path_of_fb(cluster_id)
        conf_path = path_of_fb['conf_path']
        path_of_cli = config.get_path_of_cli(cluster_id)
        conf_backup_path = path_of_cli['conf_backup_path']
        conf_backup_tag_path = os.path.join(conf_backup_path, tag)

        if not os.path.isdir(conf_backup_path):
            os.mkdir(conf_backup_path)

        # back up conf
        os.mkdir(conf_backup_tag_path)
        client = net.get_ssh(host)
        net.copy_dir_from_remote(client, conf_path, conf_backup_tag_path)
        client.close()

        logger.info('OK, {}'.format(tag))

    def cluster_backup(self, host, cluster_id, tag):
        logger.info('Backup cluster {} at {}...'.format(cluster_id, host))
        # prepare
        path_of_fb = config.get_path_of_fb(cluster_id)
        cluster_path = path_of_fb['cluster_path']
        cluster_backup_path = path_of_fb['cluster_backup_path']
        cluster_backup_tag_path = os.path.join(cluster_backup_path, tag)

        # back up cluster
        client = net.get_ssh(host)
        if not net.is_dir(client, cluster_backup_path):
            sftp = net.get_sftp(client)
            sftp.mkdir(cluster_backup_path)
            sftp.close()
        command = 'mv {} {}'.format(cluster_path, cluster_backup_tag_path)
        net.ssh_execute(client=client, command=command)
        client.close()
        logger.info('OK, {}'.format(tag))

    def conf_restore(self, host, cluster_id, tag):
        logger.debug('Restore conf to cluster {}...'.format(cluster_id))
        # prepare
        path_of_fb = config.get_path_of_fb(cluster_id)
        path_of_cli = config.get_path_of_cli(cluster_id)
        conf_path = path_of_fb['conf_path']
        conf_backup_path = path_of_cli['conf_backup_path']
        conf_backup_tag_path = os.path.join(conf_backup_path, tag)

        # restore conf
        client = net.get_ssh(host)
        net.copy_dir_to_remote(client, conf_backup_tag_path, conf_path)
        client.close()
        logger.debug('OK')

    def get_alive_redis_count(self, hosts, ports, check_owner=False):
        logger.debug('get_alive_redis_count')
        logger.debug('hosts={}, ports={}'.format(hosts, ports))
        if check_owner:
            ps_list_command = get_my_ps_list_command(ports, self.cluster_id)
        else:
            ps_list_command = get_ps_list_command(ports)
        command = '{} | wc -l'.format(ps_list_command)
        total = 0
        for host in hosts:
            client = net.get_ssh(host)
            _, stdout_msg, _ = net.ssh_execute(client=client, command=command)
            total += int(stdout_msg.strip())
        logger.debug('redis-server total={}'.format(total))
        cmd = "ps -ef | grep 'redis-rdb-to-slaves' | grep -v 'grep' | wc -l"
        redis_rdb_count = 0
        for host in hosts:
            client = net.get_ssh(host)
            _, stdout_msg, _ = net.ssh_execute(client=client, command=cmd)
            redis_rdb_count += int(stdout_msg.strip())
        logger.debug(command)
        logger.debug('redis-rbd-to-slaves total={}'.format(total))
        total += redis_rdb_count
        return total

    def get_alive_master_redis_count(self, check_owner=False):
        logger.debug('get_alive_master_redis_count')
        hosts = self.master_host_list
        ports = self.master_port_list
        alive_count = self.get_alive_redis_count(hosts, ports, check_owner)
        logger.debug('alive master count={}'.format(alive_count))
        return alive_count

    def get_alive_slave_redis_count(self, check_owner=False):
        logger.debug('get_alive_slave_redis_count')
        hosts = self.slave_host_list
        ports = self.slave_port_list
        alive_count = self.get_alive_redis_count(hosts, ports, check_owner)
        logger.debug('alive slave count={}'.format(alive_count))
        return alive_count

    def get_alive_all_redis_count(self, check_owner=False):
        logger.debug('get_alive_all_redis_count')
        total_m = self.get_alive_master_redis_count(check_owner)
        total_s = self.get_alive_slave_redis_count(check_owner)
        return total_m + total_s

    def create_cluster(self, yes=False):
        """Create cluster
        """
        logger.info('>>> Creating cluster')
        logger.debug('create cluster start')
        result = self.confirm_node_port_info(skip=yes)
        if not result:
            logger.warn('Cancel create')
            return
        m_ip_list = list(map(net.get_ip, self.master_host_list))
        targets = utils.get_ip_port_tuple_list(
            m_ip_list,
            self.master_port_list
        )
        try:
            trib.create(targets, max_slots=16384)
        except Exception as ex:
            logger.error(str(ex))
            return
        if self.slave_port_list:
            self.replicate()
        logger.info('create cluster complete.')

    def confirm_node_port_info(self, skip=False):
        replicas = config.get_replicas(self.cluster_id)
        meta = [['HOST', 'PORT', 'TYPE']]
        for node in self.master_host_list:
            for port in self.master_port_list:
                meta.append([node, port, 'MASTER'])
        for node in self.slave_host_list:
            for port in self.slave_port_list:
                meta.append([node, port, 'SLAVE'])
        table = AsciiTable(meta)
        print(table.table)
        print('replicas: {}\n'.format(replicas))
        if skip:
            return True
        msg = [
            'Do you want to proceed with the create ',
            'according to the above information?',
        ]
        yes = ask_util.askBool(''.join(msg), ['y', 'n'])
        return yes

    def stop_redis_process(self, host, ports, force=False):
        """Stop redis process
        """
        logger.debug('stop_redis_process')
        signal = 'SIGKILL' if force else 'SIGINT'
        ps_list_command = get_ps_list_command(ports)
        pid_list = "{} | awk '{{print $2}}'".format(ps_list_command)
        command = 'kill -s {} $({})'.format(signal, pid_list)
        client = net.get_ssh(host)
        net.ssh_execute(client, command, allow_status=[-1, 0, 1, 2, 123, 130])
        client.close()

    def stop_redis(self, force=False):
        """Stop redis

        :param force: If true, send SIGKILL. If not, send SIGINT
        """
        logger.debug('stop_redis')
        logger.info('Stopping master cluster of redis...')
        if self.slave_host_list:
            logger.info('Stopping slave cluster of redis...')
        total_count = len(self.master_host_list) * len(self.master_port_list)
        total_count += len(self.slave_host_list) * len(self.slave_port_list)
        max_try_count = 10
        while max_try_count > 0:
            alive_count = self.get_alive_all_redis_count()
            logger.info('cur: {} / total: {}'.format(alive_count, total_count))
            if alive_count <= 0:
                logger.info('Complete all redis process down')
                return True
            max_try_count -= 1
            if max_try_count % 3 == 0:
                for host in self.master_host_list:
                    self.stop_redis_process(host, self.master_port_list, force)
                for host in self.slave_host_list:
                    self.stop_redis_process(host, self.slave_port_list, force)
            time.sleep(1)
        raise ClusterRedisError('Fail to stop redis: max try exceed')

    def create_redis_data_directory(self, master=True, slave=True):
        """ create directory SR2_REDIS_DATA, SR2_FLASH_DB_PATH
        """
        logger.debug('create_redis_data_directory')
        if master:
            logger.info('create redis data directory in each MASTER hosts')
            self._create_redis_data_directory(
                self.master_host_list,
                self.master_port_list,
            )
        if slave and self.slave_host_list:
            logger.info('create redis data directory in each SLAVE hosts')
            self._create_redis_data_directory(
                self.slave_host_list,
                self.slave_port_list,
            )

    def _create_redis_data_directory(self, hosts, ports):
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        props_path = path_of_fb['redis_properties']
        prefix_srd = config.get_props(props_path, 'sr2_redis_data')
        prefix_sfdp = config.get_props(props_path, 'sr2_flash_db_path')
        ssd_count = config.get_props(props_path, 'ssd_count')
        user = os.environ['USER']
        for host in hosts:
            logger.info(' - {}'.format(host))
            command = ['mkdir -p']
            count = 0
            for port in ports:
                # depence: [Errno 7] Argument list too long
                if count > 100:
                    command = ' '.join(command)
                    client = net.get_ssh(host)
                    net.ssh_execute(client, command)
                    client.close()
                    command = ['mkdir -p']
                    count = 0
                count += 1
                ssd_no = config.get_sata_ssd_no(port, ssd_count)
                sr2_redis_data = '{}{}/{}'.format(
                    prefix_srd,
                    ssd_no,
                    user
                )
                sr2_flash_db_path = '{}{}/{}/db/db-{}'.format(
                    prefix_sfdp,
                    ssd_no,
                    user,
                    port
                )
                command.append(sr2_redis_data)
                command.append(sr2_flash_db_path)
            command = ' '.join(command)
            client = net.get_ssh(host)
            net.ssh_execute(client, command)
            client.close()

    def wait_until_all_redis_process_up(self):
        """Wait until all redis process up
        """
        logger.debug('wait_until_all_redis_process_up')
        logger.info('Wait until all redis process up...')
        total_count = len(self.master_host_list) * len(self.master_port_list)
        total_count += len(self.slave_host_list) * len(self.slave_port_list)
        max_try_count = 10
        while max_try_count > 0:
            alive_count = self.get_alive_all_redis_count()
            logger.info('cur: {} / total: {}'.format(alive_count, total_count))
            if alive_count >= total_count:
                logger.info('Complete all redis process up')
                if alive_count != total_count:
                    logger.warning('ClusterRedisWarning: too many process up')
                return True
            time.sleep(1)
            max_try_count -= 1
            msg = [
                'Fail to start redis: max try exceed',
                "Recommendation Command: 'monitor'"
            ]
        # raise ClusterRedisError('Fail to start redis: max try exceed')
        raise ClusterRedisError('\n'.join(msg))

    def check_hosts_connection(self, hosts=None, show_result=False):
        logger.debug('check hosts connection')
        logger.info('Check status of hosts...')
        if hosts is None:
            self.update_ip_port()
            hosts = self.all_host_list
        host_status = []
        success_count = 0
        for host in hosts:
            try:
                client = net.get_ssh(host)
                client.close()
                logger.debug('{} ssh... OK'.format(host))
                success_count += 1
                host_status.append([host, color.green('OK')])
            except HostNameError:
                show_result = True
                host_status.append([host, color.red('UNKNOWN HOST')])
                logger.debug('{} gethostbyname... FAIL'.format(host))
            except HostConnectionError:
                show_result = True
                host_status.append([host, color.red('CONNECTION FAIL')])
                logger.debug('{} connection... FAIL'.format(host))
            except SSHConnectionError:
                show_result = True
                host_status.append([host, color.red('SSH FAIL')])
                logger.debug('{} ssh... FAIL'.format(host))
        if show_result:
            table = AsciiTable([['HOST', 'STATUS']] + host_status)
            print(table.table)
        if len(hosts) != success_count:
            return False
        logger.info('OK')
        return True

    def check_include_localhost(self, hosts):
        logger.debug('check_include_localhost')
        for host in hosts:
            try:
                ip_addr = socket.gethostbyname(host)
                if ip_addr in [config.get_local_ip(), '127.0.0.1']:
                    return True
            except socket.gaierror:
                raise HostNameError(host)
        return False

    def remove_all_of_redis_log_force(self):
        logger.info('remove all of redis log')
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        sr2_redis_log = path_of_fb['sr2_redis_log']
        command = 'rm -f {}/*.log'.format(sr2_redis_log)
        for host in self.master_host_list:
            client = net.get_ssh(host)
            net.ssh_execute(client, command)
            client.close()
            logger.info(' - {}'.format(host))

    def remove_generated_config(self, client, port_list):
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        sr2_redis_conf = path_of_fb['sr2_redis_conf']
        command = [
            'export SR2_REDIS_CONF={};'.format(sr2_redis_conf),
            'rm -rf'
        ]
        count = 0
        for port in port_list:
            if count > 100:
                command = ' '.join(command)
                net.ssh_execute(client, command)
                command = [
                    'export SR2_REDIS_CONF={};'.format(sr2_redis_conf),
                    'rm -rf'
                ]
                count = 0
            count += 1
            conf_file = 'redis-{}.conf'.format(port)
            conf_file_path = os.path.join('$SR2_REDIS_CONF', conf_file)
            command.append(conf_file_path)
        command = ' '.join(command)
        net.ssh_execute(client, command)

    def _remove_data(self, client, port_list):
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        props_path = path_of_fb['redis_properties']
        prefix_srd = config.get_props(props_path, 'sr2_redis_data')
        prefix_sfdp = config.get_props(props_path, 'sr2_flash_db_path')
        ssd_count = config.get_props(props_path, 'ssd_count')
        user = os.environ['USER']
        command = ['rm -rf']
        count = 0
        for port in port_list:
            if count > 100:
                command = ' '.join(command)
                net.ssh_execute(client, command)
                command = ['rm -rf']
                count = 0
            count += 1
            ssd_no = config.get_sata_ssd_no(port, ssd_count)
            sr2_redis_data = '{}{}/{}'.format(
                prefix_srd,
                ssd_no,
                user
            )
            sr2_flash_db_path = '{}{}/{}/db/db-{}'.format(
                prefix_sfdp,
                ssd_no,
                user,
                port
            )
            command.append(sr2_flash_db_path)
            command.append('{}/appendonly-{}*.aof'.format(
                sr2_redis_data,
                port
            ))
            command.append('{}/dump-{}.rdb'.format(
                sr2_redis_data,
                port
            ))
        command = ' '.join(command)
        net.ssh_execute(client, command)

    def _remove_node_conf(self, client, port_list):
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        props_path = path_of_fb['redis_properties']
        prefix_srd = config.get_props(props_path, 'sr2_redis_data')
        ssd_count = config.get_props(props_path, 'ssd_count')
        user = os.environ['USER']
        command = ['rm -f']
        count = 0
        for port in port_list:
            if count > 100:
                command = ' '.join(command)
                net.ssh_execute(client, command)
                command = ['rm -f']
                count = 0
            count += 1
            ssd_no = config.get_sata_ssd_no(port, ssd_count)
            sr2_redis_data = '{}{}/{}'.format(prefix_srd, ssd_no, user)
            file_name = 'nodes-{}.conf'.format(port)
            file_path = os.path.join(sr2_redis_data, file_name)
            command.append(file_path)
        command = ' '.join(command)
        net.ssh_execute(client, command)

    def cluster_clean(self, master=True, slave=True):
        if master:
            logger.info('clean redis conf, node conf, db data of master')
            for host in self.master_host_list:
                logger.info(' - {}'.format(host))
                client = net.get_ssh(host)
                self.remove_generated_config(client, self.master_port_list)
                self._remove_data(client, self.master_port_list)
                self._remove_node_conf(client, self.master_port_list)
                client.close()
        if slave and self.slave_host_list:
            logger.info('clean redis conf, node conf, db data of slave')
            for host in self.slave_host_list:
                logger.info(' - {}'.format(host))
                client = net.get_ssh(host)
                self.remove_generated_config(client, self.slave_port_list)
                self._remove_data(client, self.slave_port_list)
                self._remove_node_conf(client, self.slave_port_list)
                client.close()

    def update_ip_port(self):
        logger.debug('update ip port')
        self.cluster_id = config.get_cur_cluster_id()
        self.master_host_list = config.get_master_host_list(self.cluster_id)
        self.slave_host_list = config.get_slave_host_list(self.cluster_id)
        self.master_port_list = config.get_master_port_list(self.cluster_id)
        self.slave_port_list = config.get_slave_port_list(self.cluster_id)
        m_host_list = self.master_host_list
        s_host_list = self.slave_host_list
        self.all_host_list = list(set(m_host_list + s_host_list))

    def check_conf_file_exist(self, hosts, ports):
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        sr2_redis_conf = path_of_fb['sr2_redis_conf']
        for host in hosts:
            conf_path_list = []
            res = True
            count = 0
            for port in ports:
                if count > 100:
                    client = net.get_ssh(host)
                    res = res and net.is_exist_files(client, conf_path_list)
                    client.close()
                    count = 0
                    conf_path_list = []
                count += 1
                conf_path = '{}/redis-{}.conf'.format(sr2_redis_conf, port)
                conf_path_list.append(conf_path)
            client = net.get_ssh(host)
            res = res and net.is_exist_files(client, conf_path_list)
            client.close()
            if not res:
                msg = "conf file not exist at '{}'".format(host)
                raise ClusterRedisError(msg)

    def start_redis_process(self, profile=False, master=True, slave=True):
        """ Start redis process
        """
        logger.debug('start_redis_process.')
        if master:
            self.check_conf_file_exist(
                self.master_host_list,
                self.master_port_list
            )
        if slave:
            self.check_conf_file_exist(
                self.slave_host_list,
                self.slave_port_list
            )
        current_time = time.strftime("%Y%m%d-%H%M", time.gmtime())
        if master:
            m_port = self.master_port_list
            for host in self.master_host_list:
                logger.info('Starting master nodes : {} : {} ...'.format(
                    host,
                    '|'.join(list(map(str, m_port)))
                ))
                self.run_redis_process(host, m_port, profile, current_time)
        if slave:
            s_port = self.slave_port_list
            for host in self.slave_host_list:
                logger.info('Starting slave nodes : {} : {} ...'.format(
                    host,
                    '|'.join(list(map(str, s_port)))
                ))
                self.run_redis_process(host, s_port, profile, current_time)

    def run_redis_process(self, host, ports, profile, current_time):
        logger.debug('run_redis_process')
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        sr2_redis_bin = path_of_fb['sr2_redis_bin']
        sr2_redis_conf = path_of_fb['sr2_redis_conf']
        sr2_redis_log = path_of_fb['sr2_redis_log']
        sr2_redis_lib = path_of_fb['sr2_redis_lib']
        lib_path = config.get_ld_library_path(self.cluster_id)

        # create log directory
        client = net.get_ssh(host)
        command = 'mkdir -p {}'.format(sr2_redis_log)
        net.ssh_execute(client, command)

        # make env
        env_cmd = [
            'GLOBIGNORE=*;',
            'export LD_LIBRARY_PATH={};'.format(lib_path['ld_library_path']),
            'export DYLD_LIBRARY_PATH={};'.format(
                lib_path['dyld_library_path']
            ),
            'export SR2_REDIS_BIN={};'.format(sr2_redis_bin),
            'export SR2_REDIS_CONF={};'.format(sr2_redis_conf),
            'export SR2_REDIS_LOG={};'.format(sr2_redis_log),
            'export SR2_REDIS_LIB={};'.format(sr2_redis_lib),
        ]
        if profile:
            env_cmd.append(
                'MALLOC_CONF=prof_leak:true,lg_prof_sample:0,prof_final:true;'
            )
            env_cmd.append(
                'LD_PRELOAD=$SR2_REDIS_LIB/native/libjemalloc.so;'
            )

        run_cmd = '$SR2_REDIS_BIN/redis-server'
        command = [' '.join(env_cmd)]
        count = 0
        for port in ports:
            if count > 100:
                command = ' '.join(command)
                client = net.get_ssh(host)
                net.ssh_execute(client, command)
                client.close()
                command = [' '.join(env_cmd)]
                count = 0
            count += 1
            conf_file_name = 'redis-{}.conf'.format(port)
            log_file_name = 'servers-{}-{}.log'.format(current_time, port)
            command.append('({} {} >> {} 2>&1) &'.format(
                run_cmd,
                '$SR2_REDIS_CONF/{}'.format(conf_file_name),
                '$SR2_REDIS_LOG/{}'.format(log_file_name),
            ))
        command = ' '.join(command)
        client = net.get_ssh(host)
        net.ssh_execute(client, command)
        client.close()

    def ensure_cluster_exist(self):
        logger.debug('ensure_cluster_exist')
        logger.info('Check cluster exist...')
        hosts = self.all_host_list
        for host in hosts:
            logger.info(' - {}'.format(host))
            deploy_state = DeployUtil().get_state(self.cluster_id, host)
            if deploy_state != DEPLOYED:
                raise ClusterNotExistError(self.cluster_id, host=host)
        logger.info('OK')

    @staticmethod
    def _get_ip_port_dict_using_cluster_nodes_cmd():
        def mute_formatter(outs):
            pass

        outs = RedisCliUtil.command(
            sub_cmd='cluster nodes',
            formatter=mute_formatter)
        lines = outs.splitlines()
        d = {}
        for line in lines:
            rows = line.split(' ')
            addr = rows[1]
            if 'connected' in rows:
                (host, port) = addr.split(':')
                if host not in d:
                    d[host] = [port]
                else:
                    d[host].append(port)
        return d

    def _get_master_slave_pair_list(self):
        m_count = len(self.master_host_list)
        m_port_count = len(self.master_port_list)
        ret = []
        for i, m_host in enumerate(self.master_host_list):
            for j, s_port in enumerate(self.slave_port_list):
                master_port_idx = j % m_port_count
                slave_host_idx = (i + 1 + j // m_port_count) % m_count
                ret.append([
                    m_host,  # master host
                    self.master_port_list[master_port_idx],  # master port
                    self.slave_host_list[slave_host_idx],  # slave host
                    s_port  # slave port
                ])
        return ret

    @staticmethod
    def _replicate_thread(m_ip, m_port, s_ip, s_port):
        logger.info('replicate [M] %s %s - [S] %s %s' % (
            m_ip, m_port, s_ip, s_port))
        m_ip = net.get_ip(m_ip)
        s_ip = net.get_ip(s_ip)
        trib.replicate(m_ip, m_port, s_ip, s_port)

    def replicate(self):
        threads = []
        pair_list = self._get_master_slave_pair_list()
        for m_ip, m_port, s_ip, s_port in pair_list:
            t = Thread(
                target=Center._replicate_thread,
                args=(m_ip, m_port, s_ip, s_port,))
            threads.append(t)
        for x in threads:
            x.start()
        count = 0
        for x in threads:
            x.join()
            count += 1
            logger.info('%d / %d meet complete.' % (count, len(threads)))

    def cli_config_get(self, key, host, port):
        lib_path = config.get_ld_library_path(self.cluster_id)
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        sr2_redis_bin = path_of_fb['sr2_redis_bin']
        sr2_redis_conf = path_of_fb['sr2_redis_conf']
        sr2_redis_log = path_of_fb['sr2_redis_log']
        sr2_redis_lib = path_of_fb['sr2_redis_lib']
        env_cmd = [
            'GLOBIGNORE=*;',
            'export LD_LIBRARY_PATH={};'.format(lib_path['ld_library_path']),
            'export DYLD_LIBRARY_PATH={};'.format(
                lib_path['dyld_library_path']
            ),
            'export SR2_REDIS_BIN={};'.format(sr2_redis_bin),
            'export SR2_REDIS_CONF={};'.format(sr2_redis_conf),
            'export SR2_REDIS_LOG={};'.format(sr2_redis_log),
            'export SR2_REDIS_LIB={};'.format(sr2_redis_lib),
        ]
        redis_cli_cmd = os.path.join(sr2_redis_bin, 'redis-cli')
        sub_cmd = 'config get "{}"'.format(key)
        command = '{} {} -h {} -p {} {}'.format(
            ' '.join(env_cmd),
            redis_cli_cmd,
            host,
            port,
            sub_cmd,
        )
        try:
            stdout = subprocess.check_output(command, shell=True)
            stdout = stdout.decode('utf-8')
            return stdout.strip().split()[1]
        except subprocess.CalledProcessError as ex:
            logger.debug(ex)
            return False

    def cli_config_set_all(self, key, value, hosts, ports):
        lib_path = config.get_ld_library_path(self.cluster_id)
        path_of_fb = config.get_path_of_fb(self.cluster_id)
        sr2_redis_bin = path_of_fb['sr2_redis_bin']
        sr2_redis_conf = path_of_fb['sr2_redis_conf']
        sr2_redis_log = path_of_fb['sr2_redis_log']
        sr2_redis_lib = path_of_fb['sr2_redis_lib']
        env_cmd = [
            'GLOBIGNORE=*;',
            'export LD_LIBRARY_PATH={};'.format(lib_path['ld_library_path']),
            'export DYLD_LIBRARY_PATH={};'.format(
                lib_path['dyld_library_path']
            ),
            'export SR2_REDIS_BIN={};'.format(sr2_redis_bin),
            'export SR2_REDIS_CONF={};'.format(sr2_redis_conf),
            'export SR2_REDIS_LOG={};'.format(sr2_redis_log),
            'export SR2_REDIS_LIB={};'.format(sr2_redis_lib),
        ]
        redis_cli_cmd = os.path.join(sr2_redis_bin, 'redis-cli')
        sub_cmd = 'config set {} {}'.format(key, value)
        success = True
        for host in hosts:
            for port in ports:
                command = '{} {} -h {} -p {} {}'.format(
                    ' '.join(env_cmd),
                    redis_cli_cmd,
                    host,
                    port,
                    sub_cmd,
                )
                stdout = subprocess.check_output(command, shell=True)
                if stdout.decode('utf-8').strip() != 'OK':
                    success = False
        return success
