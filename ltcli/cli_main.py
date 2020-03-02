from __future__ import print_function
from __future__ import absolute_import

import os
import time
import shutil
import socket

import click
import fire
from fire.core import FireExit
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.lexers import PygmentsLexer
from pygments.lexers.sql import SqlLexer
import paramiko
import yaml

from ltcli import log
from ltcli import net
from ltcli import config
from ltcli import utils
from ltcli import prompt
from ltcli import color
from ltcli import ask_util
from ltcli import cluster_util
from ltcli import editor
from ltcli.log import logger
from ltcli.cli import Cli
from ltcli.cluster import Cluster
from ltcli.center import Center
from ltcli.conf import Conf
from ltcli.thriftserver import ThriftServer
from ltcli.deploy_util import DeployUtil, DEPLOYED, PENDING
from ltcli.rediscli import RedisCliConfig
from ltcli.exceptions import (
    SSHConnectionError,
    HostConnectionError,
    HostNameError,
    FileNotExistError,
    YamlSyntaxError,
    PropsSyntaxError,
    PropsKeyError,
    PropsError,
    ClusterIdError,
    ClusterNotExistError,
    ClusterRedisError,
    LightningDBError,
    SSHCommandError,
    EnvError,
)


user_info = {
    'user': None,
    'print_mode': 'screen'
}


def run_monitor(n=10):
    """Run monitor command

    Monitor remote logs
    """
    host_list = config.get_master_host_list()
    cluster_id = config.get_cur_cluster_id()
    target_host = ask_util.host_for_monitor(host_list)
    logger.info('Press Ctrl-C for exit.')
    client = net.get_ssh(target_host)
    path_of_fb = config.get_path_of_fb(cluster_id)
    sr2_redis_log = path_of_fb['sr2_redis_log']
    command = 'tail -F -n {} {}/servers*'.format(n, sr2_redis_log)
    net.ssh_execute_async(client, command)


# def run_deploy_v3(cluster_id=None, history_save=True, force=False):
def run_deploy(
        cluster_id=None,
        history_save=True,
        clean=False,
        strategy="none"
):
    # validate cluster id
    if cluster_id is None:
        cluster_id = config.get_cur_cluster_id(allow_empty_id=True)
        if cluster_id < 0:
            msg = 'Select cluster first or type cluster id with argument'
            logger.error(msg)
            return
    if not cluster_util.validate_id(cluster_id):
        raise ClusterIdError(cluster_id)

    # validate option
    if not isinstance(history_save, bool):
        logger.error("option '--history-save' can use only 'True' or 'False'")
        return
    logger.debug("option '--history-save': {}".format(history_save))
    if not isinstance(clean, bool):
        logger.error("option '--clean' can use only 'True' or 'False'")
        return
    logger.debug("option '--clean': {}".format(clean))
    # if not isinstance(force, bool):
    #     logger.error("option '--force' can use only 'True' or 'False'")
    #     return
    # logger.debug("option '--force': {}".format(force))
    strategy_list = ["none", "zero-downtime"]
    if strategy not in strategy_list:
        logger.error("DeployStrategyError: '{}'. Select in {}".format(
            strategy,
            strategy_list
        ))
        return
    if strategy == "zero-downtime":
        _deploy_zero_downtime(cluster_id)
        return
    _deploy(cluster_id, history_save, clean)


def _deploy_zero_downtime(cluster_id):
    logger.debug("zero downtime update cluster {}".format(cluster_id))
    center = Center()
    center.update_ip_port()
    m_hosts = center.master_host_list
    m_ports = center.master_port_list
    s_hosts = center.slave_host_list
    s_ports = center.slave_port_list
    path_of_fb = config.get_path_of_fb(cluster_id)

    # check master alive
    m_count = len(m_hosts) * len(m_ports)
    alive_m_count = center.get_alive_master_redis_count()
    if alive_m_count < m_count:
        logger.error("There is disconnected master")
        return

    if not config.is_slave_enabled:
        logger.error("Need to slave")
        return

    # select installer
    installer_path = ask_util.installer()
    installer_name = os.path.basename(installer_path)

    # backup info
    current_time = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    conf_backup_dir = 'cluster_{}_conf_bak_{}'.format(cluster_id, current_time)
    cluster_backup_dir = 'cluster_{}_bak_{}'.format(cluster_id, current_time)
    local_ip = config.get_local_ip()

    # backup conf
    center.conf_backup(local_ip, cluster_id, conf_backup_dir)

    # backup cluster
    for host in s_hosts:
        cluster_path = path_of_fb['cluster_path']
        client = net.get_ssh(host)
        center.cluster_backup(host, cluster_id, cluster_backup_dir)
        client.close()

    # transfer & install
    logger.info('Transfer installer and execute...')
    for host in m_hosts:
        logger.info(' - {}'.format(host))
        client = net.get_ssh(host)
        cmd = 'mkdir -p {0} && touch {0}/.deploy.state'.format(cluster_path)
        net.ssh_execute(client=client, command=cmd)
        client.close()
        DeployUtil().transfer_installer(host, cluster_id, installer_path)
        try:
            DeployUtil().install(host, cluster_id, installer_name)
        except SSHCommandError as ex:
            msg = "Fail to execute installer '{}'".format(installer_path)
            logger.error(msg)
            logger.exception(ex)
            return

    # restore conf
    center.conf_restore(local_ip, cluster_id, conf_backup_dir)

    # set deploy state complete
    for node in m_hosts:
        path_of_fb = config.get_path_of_fb(cluster_id)
        cluster_path = path_of_fb['cluster_path']
        client = net.get_ssh(node)
        cmd = 'rm -rf {}'.format(os.path.join(cluster_path, '.deploy.state'))
        net.ssh_execute(client=client, command=cmd)
        client.close()

    # restart slave
    center.stop_redis(master=False)
    center.configure_redis(master=False)
    center.sync_conf()
    center.start_redis_process(master=False)
    center.wait_until_all_redis_process_up()

    # check slave is alive
    slaves_for_failover = center.check_all_master_have_alive_slave()

    key = 'cluster-node-timeout'
    origin_m_value = center.cli_config_get(key, m_hosts[0], m_ports[0])
    origin_s_value = center.cli_config_get(key, s_hosts[0], s_ports[0])
    logger.info('config set: cluster-node-timeout 2000')
    RedisCliConfig().set(key, '2000', all=True)

    # cluster failover (with no option)
    logger.info("Replace master to slave")
    logger.debug(slaves_for_failover)
    try_count = 0
    while try_count < 10:
        try_count += 1
        success = True
        for slave_addr in slaves_for_failover:
            host, port = slave_addr.split(':')
            # In some cases, the cluster failover is not complete
            # even if stdout is OK
            # If redis changed to master completely,
            # return 'ERR You should send CLUSTER FAILOVER to a slave'
            stdout = center.run_failover("{}:{}".format(host, port))
            logger.debug("failover {}:{} {}".format(host, port, stdout))
            if stdout != "ERR You should send CLUSTER FAILOVER to a slave":
                success = False
        if success:
            break
        logger.info("retry: {}".format(try_count))
        time.sleep(5)
    logger.info('restore config: cluster-node-timeout')
    center.cli_config_set_all(key, origin_m_value, m_hosts, m_ports)
    center.cli_config_set_all(key, origin_s_value, s_hosts, s_ports)
    if not success:
        logger.error("Fail to cluster failover")
        return

    # restart master (current slave)
    center.stop_redis(slave=False)
    center.configure_redis(slave=False)
    center.sync_conf()
    center.start_redis_process(slave=False)
    center.wait_until_all_redis_process_up()

    # change host info of redis.properties
    props_path = path_of_fb['redis_properties']
    after_m_ports = list(set(map(
        lambda x: int(x.split(':')[1]),
        slaves_for_failover
    )))
    after_s_ports = list(set(s_ports + m_ports) - set(after_m_ports))
    logger.debug("master port {}".format(m_ports))
    logger.debug("slave port {}".format(s_ports))
    key = 'sr2_redis_master_ports'
    logger.debug("after master port {}".format(after_m_ports))
    value = cluster_util.convert_list_2_seq(after_m_ports)
    logger.debug("converted {}".format(value))
    config.set_props(props_path, key, value)
    key = 'sr2_redis_slave_ports'
    logger.debug("after slave port {}".format(after_s_ports))
    value = cluster_util.convert_list_2_seq(after_s_ports)
    logger.debug("converted {}".format(value))
    config.set_props(props_path, key, value)


def _deploy(cluster_id, history_save, clean):
    deploy_state = DeployUtil().get_state(cluster_id)
    if deploy_state == DEPLOYED:
        q = [
            color.YELLOW,
            '(Watch out) ',
            'Cluster {} is already deployed. '.format(cluster_id),
            'Do you want to deploy again?',
            color.ENDC,
        ]
        yes = ask_util.askBool(''.join(q), default='n')
        if not yes:
            logger.info('Cancel deploy.')
            return

    restore_yes = None
    current_time = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    cluster_backup_dir = 'cluster_{}_bak_{}'.format(cluster_id, current_time)
    conf_backup_dir = 'cluster_{}_conf_bak_{}'.format(cluster_id, current_time)
    tmp_backup_dir = 'cluster_{}_conf_bak_{}'.format(cluster_id, 'tmp')
    meta = [['NAME', 'VALUE']]
    path_of_fb = config.get_path_of_fb(cluster_id)
    conf_path = path_of_fb['conf_path']
    props_path = path_of_fb['redis_properties']
    cluster_path = path_of_fb['cluster_path']
    path_of_cli = config.get_path_of_cli(cluster_id)
    conf_backup_path = path_of_cli['conf_backup_path']
    tmp_backup_path = os.path.join(conf_backup_path, tmp_backup_dir)
    local_ip = config.get_local_ip()

    # ask installer
    installer_path = ask_util.installer()
    installer_name = os.path.basename(installer_path)
    meta.append(['installer', installer_name])

    # ask restore conf
    if deploy_state == DEPLOYED:
        restore_yes = ask_util.askBool('Do you want to restore conf?')
        meta.append(['restore', restore_yes])

    # input props
    hosts = []
    if deploy_state == DEPLOYED:
        if restore_yes:
            meta += DeployUtil().get_meta_from_props(props_path)
            hosts = config.get_props(props_path, 'sr2_redis_master_hosts')
        else:
            if os.path.exists(tmp_backup_path):
                q = 'There is a history of modification. Do you want to load?'
                yes = ask_util.askBool(q)
                if not yes:
                    shutil.rmtree(tmp_backup_path)
            if not os.path.exists(tmp_backup_path):
                shutil.copytree(conf_path, tmp_backup_path)
            tmp_props_path = os.path.join(tmp_backup_path, 'redis.properties')
            editor.edit(tmp_props_path, syntax='sh')
            meta += DeployUtil().get_meta_from_props(tmp_props_path)
            hosts = config.get_props(tmp_props_path, 'sr2_redis_master_hosts')
    else:
        # new deploy
        props_dict = ask_util.props(cluster_id, save=history_save)
        hosts = props_dict['hosts']
        meta += DeployUtil().get_meta_from_dict(props_dict)
    utils.print_table(meta)

    msg = [
        'Do you want to proceed with the deploy ',
        'accroding to the above information?',
    ]
    yes = ask_util.askBool(''.join(msg))
    if not yes:
        logger.info("Cancel deploy.")
        return

    # check node status
    success = Center().check_hosts_connection(hosts, True)
    if not success:
        logger.error('There are unavailable host.')
        return
    logger.debug('Connection of all hosts ok.')
    success = Center().check_include_localhost(hosts)
    if not success:
        logger.error('Must include localhost.')
        return

    # if pending, delete legacy on each hosts
    for host in hosts:
        if DeployUtil().get_state(cluster_id, host) == PENDING:
            client = net.get_ssh(host)
            command = 'rm -rf {}'.format(cluster_path)
            net.ssh_execute(client=client, command=command)
            client.close()

    # added_hosts = post_hosts - pre_hosts
    logger.info('Checking for cluster exist...')
    added_hosts = set(hosts)
    meta = []
    if deploy_state == DEPLOYED:
        pre_hosts = config.get_props(props_path, 'sr2_redis_master_hosts')
        added_hosts -= set(pre_hosts)
    can_deploy = True
    for host in added_hosts:
        client = net.get_ssh(host)
        if net.is_exist(client, cluster_path):
            meta.append([host, color.red('CLUSTER EXIST')])
            can_deploy = False
            continue
        meta.append([host, color.green('CLEAN')])
    if meta:
        utils.print_table([['HOST', 'STATUS']] + meta)
    if not can_deploy:
        logger.error('Cluster information exist on some hosts.')
        return
        # if not force:
        #     logger.error("If you trying to force, use option '--force'")
        #     return
    logger.info('OK')

    # cluster stop and clean
    if deploy_state == DEPLOYED:
        center = Center()
        cur_cluster_id = config.get_cur_cluster_id(allow_empty_id=True)
        run_cluster_use(cluster_id)
        center.update_ip_port()
        center.stop_redis()
        if clean:
            center.remove_all_of_redis_log_force()
            center.cluster_clean()
        run_cluster_use(cur_cluster_id)

    # backup conf
    if deploy_state == DEPLOYED:
        Center().conf_backup(local_ip, cluster_id, conf_backup_dir)

    # backup cluster
    backup_hosts = []
    if deploy_state == DEPLOYED:
        backup_hosts += set(pre_hosts)
    # if force:
    #     backup_hosts += added_hosts
    for host in backup_hosts:
        cluster_path = path_of_fb['cluster_path']
        client = net.get_ssh(host)
        Center().cluster_backup(host, cluster_id, cluster_backup_dir)
        client.close()

    # transfer & install
    logger.info('Transfer installer and execute...')
    for host in hosts:
        logger.info(' - {}'.format(host))
        client = net.get_ssh(host)
        cmd = 'mkdir -p {0} && touch {0}/.deploy.state'.format(cluster_path)
        net.ssh_execute(client=client, command=cmd)
        client.close()
        DeployUtil().transfer_installer(host, cluster_id, installer_path)
        try:
            DeployUtil().install(host, cluster_id, installer_name)
        except SSHCommandError as ex:
            msg = "Fail to execute installer '{}'".format(installer_path)
            logger.error(msg)
            logger.exception(ex)
            return

    # setup props
    if deploy_state == DEPLOYED:
        if restore_yes:
            tag = conf_backup_dir
        else:
            tag = tmp_backup_dir
        Center().conf_restore(local_ip, cluster_id, tag)
    else:
        key = 'sr2_redis_master_hosts'
        config.make_key_enable(props_path, key)
        config.set_props(props_path, key, props_dict['hosts'])

        key = 'sr2_redis_master_ports'
        config.make_key_enable(props_path, key)
        value = cluster_util.convert_list_2_seq(props_dict['master_ports'])
        config.set_props(props_path, key, value)

        key = 'sr2_redis_slave_hosts'
        config.make_key_enable(props_path, key)
        config.set_props(props_path, key, props_dict['hosts'])
        config.make_key_disable(props_path, key)

        if props_dict['replicas'] > 0:
            key = 'sr2_redis_slave_hosts'
            config.make_key_enable(props_path, key)

            key = 'sr2_redis_slave_ports'
            config.make_key_enable(props_path, key)
            value = cluster_util.convert_list_2_seq(props_dict['slave_ports'])
            config.set_props(props_path, key, value)

        key = 'ssd_count'
        config.make_key_enable(props_path, key)
        config.set_props(props_path, key, props_dict['ssd_count'])

        key = 'sr2_redis_data'
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_disable(props_path, key)
        config.set_props(props_path, key, props_dict['prefix_of_db_path'])

        key = 'sr2_redis_db_path'
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_disable(props_path, key)
        config.set_props(props_path, key, props_dict['prefix_of_db_path'])

        key = 'sr2_flash_db_path'
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_enable(props_path, key, v1_flg=True)
        config.make_key_disable(props_path, key)
        config.set_props(props_path, key, props_dict['prefix_of_db_path'])

    # synk props
    logger.info('Sync conf...')
    for node in hosts:
        if socket.gethostbyname(node) in config.get_local_ip_list():
            continue
        client = net.get_ssh(node)
        if not client:
            logger.error("ssh connection fail: '{}'".format(node))
            return
        net.copy_dir_to_remote(client, conf_path, conf_path)
        client.close()

    # set deploy state complete
    if os.path.exists(tmp_backup_path):
        shutil.rmtree(tmp_backup_path)
    for node in hosts:
        path_of_fb = config.get_path_of_fb(cluster_id)
        cluster_path = path_of_fb['cluster_path']
        client = net.get_ssh(node)
        cmd = 'rm -rf {}'.format(os.path.join(cluster_path, '.deploy.state'))
        net.ssh_execute(client=client, command=cmd)
        client.close()

    logger.info('Complete to deploy cluster {}.'.format(cluster_id))
    Cluster().use(cluster_id)


def run_cluster_use(cluster_id):
    print_mode = user_info['print_mode']
    c = Cluster(print_mode)
    c.use(cluster_id)


def run_import_conf():
    def _to_config_yaml(
          cluster_id, release, nodes, master_start_port, master_end_port,
          master_enabled, slave_start_port, slave_end_port, slave_enabled,
          ssd_count):
        conf = {}
        conf['release'] = release
        conf['nodes'] = nodes
        conf['ssd'] = {}
        conf['master_ports'] = {}
        conf['slave_ports'] = {}
        conf['master_ports']['from'] = int(master_start_port)
        conf['master_ports']['to'] = int(master_end_port)
        conf['master_ports']['enabled'] = bool(master_enabled)
        conf['slave_ports']['from'] = int(slave_start_port)
        conf['slave_ports']['to'] = int(slave_end_port)
        conf['slave_ports']['enabled'] = bool(slave_enabled)
        conf['ssd']['count'] = int(ssd_count)

        root_of_cli_config = config.get_root_of_cli_config()
        cluster_base_path = os.path.join(root_of_cli_config, 'clusters')
        if not os.path.isdir(cluster_base_path):
            os.mkdir(cluster_base_path)
        cluster_path = os.path.join(root_of_cli_config, 'clusters', cluster_id)
        if not os.path.isdir(cluster_path):
            os.mkdir(cluster_path)
        yaml_path = os.path.join(cluster_path, 'config.yaml')
        with open(yaml_path, 'w') as fd:
            yaml.dump(conf, fd, default_flow_style=False)

    def _import_from_fb_to_cli_conf(rp_exists):
        for cluster_id in rp_exists:
            path_of_fb = config.get_path_of_fb(cluster_id)
            rp = path_of_fb['redis_properties']
            d = config.get_props_as_dict(rp)
            nodes = d['sr2_redis_master_hosts']
            master_start_port = 0
            master_end_port = 0
            slave_start_port = 0
            slave_end_port = 0
            master_enabled = 'sr2_redis_master_ports' in d
            slave_enabled = 'sr2_redis_slave_ports' in d
            if master_enabled:
                master_start_port = min(d['sr2_redis_master_ports'])
                master_end_port = max(d['sr2_redis_master_ports'])
            if slave_enabled:
                slave_start_port = min(d['sr2_redis_slave_ports'])
                slave_end_port = max(d['sr2_redis_slave_ports'])
            ssd_count = d['ssd_count']
            _to_config_yaml(
                cluster_id=cluster_id,
                release='',
                nodes=nodes,
                master_start_port=master_start_port,
                master_end_port=master_end_port,
                master_enabled=master_enabled,
                slave_start_port=slave_start_port,
                slave_end_port=slave_end_port,
                slave_enabled=slave_enabled,
                ssd_count=ssd_count)
            logger.info('Save config.yaml from redis.properties')

    def _get_cluster_ids_from_fb():
        cluster_id = config.get_cur_cluster_id(allow_empty_id=True)
        path_of_fb = config.get_path_of_fb(cluster_id)
        base_directory = path_of_fb['base_directory']
        dirs = [f for f in os.listdir(base_directory)
                if not os.path.isfile(os.path.join(base_directory, f))]
        cluster_ids = [d.split('_')[1] for d in dirs if 'cluster_' in d]
        return cluster_ids

    cluster_ids = _get_cluster_ids_from_fb()
    root_of_cli_config = config.get_root_of_cli_config()

    rp_exists = []
    rp_not_exists = []
    dest_folder_exists = []
    meta = [['cluster_id', 'state']]
    for cluster_id in cluster_ids:
        path_of_fb = config.get_path_of_fb(cluster_id)
        rp = path_of_fb['redis_properties']
        dest_path = os.path.join(root_of_cli_config, 'clusters', cluster_id)
        dest_path = os.path.join(dest_path, 'config.yaml')
        cluster_path = path_of_fb['cluster_path']
        deploy_state = os.path.join(cluster_path, '.deploy.state')
        if os.path.exists(dest_path):
            dest_folder_exists.append(cluster_id)
            meta.append([cluster_id, 'SKIP(dest_exist)'])
        elif os.path.isfile(rp) and not os.path.isfile(deploy_state):
            rp_exists.append(cluster_id)
            meta.append([cluster_id, 'IMPORT'])
        else:
            rp_not_exists.append(cluster_id)
            meta.append([cluster_id, 'SKIP(broken)'])

    logger.info('Diff fb and cli conf folders.')
    utils.print_table(meta)
    if rp_exists:
        return
    import_yes = ask_util.askBool('Do you want to import conf?', ['y', 'n'])
    if not import_yes:
        return

    _import_from_fb_to_cli_conf(rp_exists)


def run_exit():
    """EXit ltcli
    """
    # empty function for docs of fire
    pass


def run_clear():
    """Clear screen
    """
    # empty function for docs of fire
    pass


class Command(object):
    """This is LightningDB command line.
We use python-fire(https://github.com/google/python-fire)
for automatically generating CLIs

    - deploy: install LightningDB package to nodes
    - c: change cluster #, alias of cluster use
    - cluster: trib.rb cluster wrapper
    - cli: redis-cli command wrapper
    - conf: edit conf file
    - monitor: monitor redis logs
    - thriftserver: thriftserver command
    - ths: alias of thriftserver
    - ll: change log level to debug ltcli
    - exit: exit ltcli
    - clear: clear screen
 """

    def __init__(self):
        """Member variables will be cli
        """
        # pylint: disable=invalid-name
        # cli command naming is not have to follow snake_caes
        self.deploy = run_deploy
        self.c = run_cluster_use
        self.cluster = Cluster()
        self.cli = Cli()
        self.conf = Conf()
        self.monitor = run_monitor
        self.thriftserver = ThriftServer()
        self.ths = ThriftServer()
        self.ll = log.set_level
        self.exit = run_exit
        self.clear = run_clear


def _handle(text):
    if text == '':
        return
    if text == 'clear':
        utils.clear_screen()
        return
    text = text.replace('-- --help', '?')
    text = text.replace('--help', '?')
    text = text.replace('?', '-- --help')
    try:
        fire.Fire(
            component=Command,
            command=text)
    except KeyboardInterrupt:
        logger.warning('\b\bCanceled')
    except KeyError as ex:
        logger.warn('[%s] command fail' % text)
        logger.exception(ex)
    except TypeError as ex:
        logger.exception(ex)
    except IOError as ex:
        if ex.errno == 2:
            logger.error("{}: '{}'".format('FileNotExistError', ex.filename))
        else:
            logger.exception(ex)
    except EOFError:
        logger.warning('\b\bCanceled')
    except utils.CommandError as ex:
        logger.exception(ex)
    except FireExit as ex:
        pass
    except (
            HostNameError,
            HostConnectionError,
            SSHConnectionError,
            FileNotExistError,
            YamlSyntaxError,
            PropsSyntaxError,
            PropsKeyError,
            PropsError,
            SSHCommandError,
            ClusterRedisError,
            ClusterNotExistError,
            ClusterIdError,
            EnvError,
    ) as ex:
        logger.error('{}: {}'.format(ex.class_name(), str(ex)))
    except LightningDBError as ex:
        logger.error('[ErrorCode {}] {}'.format(ex.error_code, str(ex)))
    except BaseException as ex:
        logger.exception(ex)


def _initial_check():
    try:
        # Simple check to see if ssh access to localhost is possible
        net.get_ssh('localhost')
    except paramiko.ssh_exception.SSHException:
        logger.error('Need to ssh-keygen for localhost')
        exit(1)
    cli_config = config.get_cli_config()
    try:
        base_directory = cli_config['base_directory']
    except KeyError:
        pass
    except TypeError:
        root_of_cli_config = config.get_root_of_cli_config()
        conf_path = os.path.join(root_of_cli_config, 'config')
        os.system('rm {}'.format(conf_path))
        base_directory = None
    if not base_directory or not base_directory.startswith(('~', '/')):
        base_directory = ask_util.base_directory()
    base_directory = os.path.expanduser(base_directory)
    if not os.path.isdir(base_directory):
        os.system('mkdir -p {}'.format(base_directory))


def _validate_cluster_id(cluster_id):
    try:
        if cluster_id is None:
            cluster_id = config.get_cur_cluster_id(allow_empty_id=True)
        elif not utils.is_number(cluster_id):
            raise ClusterIdError(cluster_id)
        cluster_id = int(cluster_id)
        run_cluster_use(cluster_id)
        return cluster_id
    except (ClusterIdError, ClusterNotExistError) as ex:
        logger.warning(ex)
        cluster_id = -1
        run_cluster_use(cluster_id)
        return cluster_id


def print_version():
    here = os.path.abspath(os.path.dirname(__file__))
    about = {}
    with open(os.path.join(here, '__version__.py'), 'r') as f:
        exec(f.read(), about)
    version = about['__version__']
    print('ltcli version {}'.format(version))


@click.command()
@click.option('-c', '--cluster_id', default=None, help='ClusterId.')
@click.option('-d', '--debug', default=False, help='Debug.')
@click.option('-v', '--version', is_flag=True, help='Version.')
def main(cluster_id, debug, version):
    if version:
        print_version()
        return
    _initial_check()
    if debug:
        log.set_mode('debug')

    logger.debug('Start ltcli')

    cluster_id = _validate_cluster_id(cluster_id)

    history = os.path.join(config.get_root_of_cli_config(), 'cli_history')
    session = PromptSession(
        lexer=PygmentsLexer(SqlLexer),
        history=FileHistory(history),
        auto_suggest=AutoSuggestFromHistory(),
        style=utils.style)
    while True:
        try:
            p = prompt.get_cli_prompt()
            text = session.prompt(p, style=utils.style)
            if text == "exit":
                break
            if 'ltcli' in text:
                old = text
                text = text.replace('ltcli', '')
                logger.info('> You can use "%s" instead of "%s"' % (text, old))
            _handle(text)
        except KeyboardInterrupt:
            continue
        except EOFError:
            break


if __name__ == '__main__':
    # pylint: disable=no-value-for-parameter
    # Parameter used by Click
    main()
