import os
import re

# pylint: disable=unused-import
# using like 'ask_util.askBool'
from ask import ask, askInt, askBool

from ltcli.log import logger
from ltcli import config
from ltcli import net
from ltcli import utils


START_PORT = 18000
MASTER_OFFSET = 100
SLAVE_OFFSET = 50
PORT_MININUM = 18000
PORT_MAXIMUM = 65535


def hosts(save, default=None):
    logger.debug('ask host')
    deploy_history = config.get_deploy_history()
    if not default:
        default = deploy_history['hosts']
    q = 'Please type host list separated by comma(,)'
    result = ask(q, default=', '.join(default))
    result = list(map(lambda x: x.strip(), result.split(',')))
    if save:
        deploy_history['hosts'] = result
        config.save_deploy_history(deploy_history)
    logger.info('OK, {}'.format(result))
    return result


def installer():
    '''
    Select installer from list of '$FBPATH/releases'
    or input absolute path of file directly
    return installer path
    '''
    logger.debug('ask installer')
    path_of_cli = config.get_path_of_cli(None)
    release_path = path_of_cli['release_path']
    if not os.path.exists(release_path):
        os.mkdir(release_path)
    installer_list = net.get_installers_from_fb_s3()
    buf = os.listdir(release_path)
    buf = list(filter(lambda x: x != '.gitignore', buf))
    pattern = '.download'
    buf = list(filter(lambda x: pattern not in x, buf))
    for file_name in buf:
        installer_list.append({
            'name': file_name,
            'url': os.path.join(release_path, file_name),
            'type': 'local',
        })

    # formatting msg
    formatted = []
    for i, obj in enumerate(installer_list):
        formatted.append('    ({index}) [{type}] {name}'.format(
            index=i+1,
            name=obj['name'],
            type=obj['type'].upper(),
        ))
    msg = [
        'Select installer',
        '',
        '    [ INSTALLER LIST ]',
        '{}\n'.format('\n'.join(formatted)),
        'Please enter the number, file path or url of the installer you want to use.',
        "you can also add file in list by copy to '$FBPATH/releases/'",
    ]
    if not installer_list:
        msg = [
            'Select installer',
            '',
            '    [ INSTALLER LIST ]',
            '    (empty)\n\n'
            'Please enter file path or url of the installer you want to use',
            "you can also add file in list by copy to '$FBPATH/releases/'",
        ]

    result = ask('\n'.join(msg))
    while True:
        result = result.strip()
        if installer_list and utils.is_number(result):
            # case: select in list
            result = int(result) - 1
            if result in range(0, len(installer_list)):
                selected = installer_list[result]
                if selected['type'] == 'download':
                    url = selected['url']
                    file_name = selected['name']
                    installer_path = os.path.join(release_path, file_name)
                    success = net.download_file(url, installer_path)
                    if success:
                        logger.info('OK, {}'.format(file_name))
                        return installer_path
                    msg = [
                        "Fail to download from '{}', ".format(url),
                        'try again.'
                    ]
                    logger.error(''.join(msg))
                if selected['type'] == 'local':
                    ret = selected['url']
                    logger.debug('Select insaller in list: {}'.format(ret))
                    logger.info('OK, {}'.format(selected['name']))
                    return os.path.expanduser(ret)
            msg = [
                'Choose a number ',
                'between 1 and {}'.format(len(installer_list)),
                ', please try again'
            ]
            logger.error(''.join(msg))
        elif result.startswith(('~', '/')):
            # case: type path
            if os.path.isfile(os.path.expanduser(result)):
                logger.debug('Select insaller by path: {}'.format(result))
                logger.info('OK, {}'.format(os.path.basename(result)))
                return os.path.expanduser(result)
            msg = [
                "File not existed: '{}'".format(result),
                ', please try again'
            ]
            logger.error(''.join(msg))
        elif result.startswith(('http://', 'https://')):
            # case: type url
            url = result
            file_name = url.split('?')[0].split('/')[-1]
            installer_path = os.path.join(release_path, file_name)
            success = net.download_file(url, installer_path)
            if success:
                logger.info('OK, {}'.format(file_name))
                return installer_path
            logger.error("Fail to download from '{}', try again".format(url))
        else:
            msg = [
                "Invalid input: '{}', ".format(result),
                "please try again",
            ]
            logger.error(''.join(msg))
        result = ask('')


def port_range_safe(port):
    if port < PORT_MININUM:
        return False
    if port > PORT_MAXIMUM:
        return False
    return True


def master_ports(save, cluster_id, default_count=None):
    logger.debug('ask master ports')
    deploy_history = config.get_deploy_history()
    if not default_count:
        default_count = deploy_history['master_count']
    q = 'How many masters would you like to create on each host?'
    m_count = int(askInt(q, default=str(default_count)))
    if m_count <= 0:
        logger.warn("The number of master must be greater than 0. try again.")
        return master_ports(cluster_id, default_count)
    logger.info('OK, {}'.format(m_count))
    if save:
        deploy_history['master_count'] = m_count
        config.save_deploy_history(deploy_history)

    start_m_ports = START_PORT + cluster_id * MASTER_OFFSET
    end_m_ports = start_m_ports + m_count - 1
    if start_m_ports == end_m_ports:
        default_m_ports = str(start_m_ports)
    else:
        default_m_ports = '{}-{}'.format(start_m_ports, end_m_ports)

    q = [
        'Please type ports separate with comma(,) ',
        'and use hyphen(-) for range.',
    ]
    while True:
        result = ask(''.join(q), default=default_m_ports)
        result = list(map(lambda x: x.strip(), result.split(',')))
        valid = True
        m_ports = set()
        pattern = re.compile('[0-9]+-[0-9]+')
        for item in result:
            # range number
            matched = pattern.match(item)
            if matched:
                s, e = map(int, item.split('-'))
                if s > e:
                    logger.error('Invalid range: {}'.format(item))
                    valid = False
                    break
                m_ports.update(range(s, e + 1))
                continue
            # single number
            elif utils.is_number(item):
                m_ports.add(int(item))
                continue
            else:
                logger.error('Invalid input: {}'.format(item))
                valid = False
                break
        if not valid:
            continue
        out_of_range = []
        for port in m_ports:
            if not port_range_safe(port):
                out_of_range.append(port)
        if out_of_range:
            msg = 'Use port between {} and {}: {}'.format(
                PORT_MININUM,
                PORT_MAXIMUM,
                out_of_range,
            )
            logger.error(msg)
            continue
        if valid and len(m_ports) != m_count:
            q2 = [
                "You type count '{}' at first, ".format(m_count),
                "but now count is '{}'. ".format(len(m_ports)),
                'try again.'
            ]
            logger.error(''.join(q2))
            continue
        if valid:
            break
    m_ports = sorted(list(m_ports))
    logger.info('OK, {}'.format(result))
    return m_ports


def replicas(save, default=None):
    logger.debug('ask replicas')
    deploy_history = config.get_deploy_history()
    if not default:
        default = deploy_history['replicas']
    q = 'How many replicas would you like to create on each master?'
    result = int(askInt(q, default=str(default)))
    if result < 0:
        msg = [
            'The number of master must be greater than or equal to 0.',
            'try again.',
        ]
        logger.error(' '.join(msg))
        return replicas(save, default=default)
    if save:
        deploy_history['replicas'] = result
        config.save_deploy_history(deploy_history)
    logger.info('OK, {}'.format(result))
    return result


def slave_ports(cluster_id, m_count, replicas_count):
    logger.debug('ask slave ports')
    if replicas_count <= 0:
        logger.debug('return empty list')
        return []
    s_count = m_count * replicas_count
    start_s_ports = START_PORT + (cluster_id * MASTER_OFFSET) + SLAVE_OFFSET
    end_s_ports = start_s_ports + s_count - 1
    if start_s_ports == end_s_ports:
        default_s_ports = str(start_s_ports)
    else:
        default_s_ports = '{}-{}'.format(start_s_ports, end_s_ports)
    q = [
        'Please type ports separate with comma(,) ',
        'and use hyphen(-) for range.',
    ]

    while True:
        result = ask(''.join(q), default=default_s_ports)
        result = list(map(lambda x: x.strip(), result.split(',')))
        valid = True
        s_ports = set()
        p = re.compile('[0-9]+-[0-9]+')
        for item in result:
            # range number
            m = p.match(item)
            if m:
                s, e = map(int, item.split('-'))
                if s > e:
                    logger.error('Invalid range: {}'.format(item))
                    valid = False
                    break
                s_ports.update(range(s, e + 1))
                continue
            # single number
            elif utils.is_number(item):
                s_ports.add(int(item))
                continue
            else:
                logger.error('Invalid input: {}'.format(item))
                valid = False
                break
        out_of_range = []
        for port in s_ports:
            if not port_range_safe(port):
                out_of_range.append(port)
        if out_of_range:
            logger.error('Use port between {} and {}: {}'.format(
                PORT_MININUM,
                PORT_MAXIMUM,
                out_of_range
            ))
            continue
        if valid and len(s_ports) != s_count:
            real_replicas_count = len(s_ports) / float(m_count)
            msg = [
                "You type replicas '{}' at first, ".format(replicas),
                "but now count is '{}'. ".format(real_replicas_count),
                'try again.'
            ]
            logger.error(''.join(msg))
            continue
        if valid:
            break
    s_ports = sorted(list(s_ports))
    logger.info('OK, {}'.format(result))
    return s_ports


def ssd_count(save, default=None):
    logger.debug('ask ssd count')
    deploy_history = config.get_deploy_history()
    if not default:
        default = deploy_history['ssd_count']
    q = 'How many ssd would you like to use?'
    result = int(askInt(q, default=str(default)))
    if result <= 0:
        logger.warn("The number of ssd must be greater than 0. try again.")
        return ssd_count(save=save, default=default)
    if save:
        deploy_history['ssd_count'] = result
        config.save_deploy_history(deploy_history)
    logger.info('OK, {}'.format(result))
    return result


def base_directory(default='~/tsr2'):
    logger.debug('ask base directory')
    result = ask('Type base directory for lightningdb', default=default)
    if not result.startswith(('~', '/')):
        logger.error("Invalid path: '{}', try again".format(result))
        return base_directory()
    logger.info('OK, {}'.format(result))
    cli_config = config.get_cli_config()
    cli_config['base_directory'] = result
    config.save_cli_config(cli_config)
    return result


def prefix_of_db_path(save, default=None):
    logger.debug('ask_prefix_of_db_path')
    deploy_history = config.get_deploy_history()
    if not default:
        default = deploy_history['prefix_of_db_path']
    q = 'Type prefix of db path'
    result = ask(q, default=default)
    result = result.strip()
    if save:
        deploy_history['prefix_of_db_path'] = result
        config.save_deploy_history(deploy_history)
    logger.info('OK, {}'.format(result))
    return result


def props(cluster_id, save):
    ret = {}
    ret['hosts'] = hosts(save)
    m_ports = master_ports(save, cluster_id)
    ret['master_ports'] = m_ports
    ret['replicas'] = replicas(save)
    m_count = len(m_ports)
    s_ports = slave_ports(cluster_id, m_count, ret['replicas'])
    ret['slave_ports'] = s_ports
    ret['ssd_count'] = int(ssd_count(save))
    ret['prefix_of_db_path'] = prefix_of_db_path(save)
    return ret


def host_for_monitor(host_list):
    formatted = []
    for i, v in enumerate(host_list):
        formatted.append('    ({}) {}'.format(i + 1, v))
    msg = [
        'Select host',
        '',
        '   [ HOST LIST ]',
        '{}\n'.format('\n'.join(formatted)),
        'Please enter the number you want to see log.',
    ]
    target_num = int(askInt('\n'.join(msg), default='1'))
    while True:
        if target_num > 0 and target_num <= len(host_list):
            break
        msg = [
            'Choose a number ',
            'between 1 and {}'.format(len(host_list)),
            ', please try again'
        ]
        logger.error(''.join(msg))
        target_num = int(askInt(''))
    return host_list[target_num - 1]
