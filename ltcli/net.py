from __future__ import print_function

import errno
import socket
import time
from threading import Thread
import os
import sys
import shutil

import paramiko
import requests

from ltcli import parser, message
from ltcli.log import logger
from ltcli.exceptions import (
    SSHConnectionError,
    HostConnectionError,
    HostNameError,
    SSHCommandError,
)


def get_ssh(host, port=22):
    """Create SSHClient, connect TCP, and return it

    :param host: host
    :param port: port
    :return: socket (SSHClient)
    """
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.load_system_host_keys()
        client.connect(hostname=host, port=port)
        client.hostname = host
        client.port = port
        return client
    except paramiko.ssh_exception.NoValidConnectionsError:
        raise HostConnectionError(host)
    except paramiko.ssh_exception.AuthenticationException:
        raise SSHConnectionError(host)
    except socket.gaierror:
        raise HostNameError(host)


def get_sftp(client):
    """Open sftp

    :param client: SSHClient instance
    :return: opened sftp instance
    """
    try:
        sftp = client.open_sftp()
        return sftp
    except Exception as e:
        logger.debug(e)


def __ssh_execute_async_thread(channel, command):
    channel.exec_command(command)
    while True:
        if channel.exit_status_ready():
            break
        try:
            msg = channel.recv(4096)
            print(msg.decode('utf-8'))
        except socket.error as e:
            err = e.args[0]
            if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                time.sleep(1)
                continue
            else:
                print(e)
                break


def ssh_execute_async(client, command):
    """Execute ssh asynchronous

    This for for not terminating process (like tail -f)

    :param client: SSHClient
    :param command: command
    """
    channel = client.get_transport().open_session()
    t = Thread(
        target=__ssh_execute_async_thread,
        args=(channel, command,))
    t.daemon = True
    t.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        channel.close()


def ssh_bulk_execute(hosts, command, allow_status=[0]):
    """
    hosts = [
        '192.168.1.1',
        '192.168.1.2',
        '192.168.1.3',
        '192.168.1.4',
    ]
    commmand = 'cp A B'
    """
    def _ssh_exeute_thread(client, command, allow_status, outputs):
        output = ssh_execute(client, command, allow_status)
        outputs.append(output)
    ts = []
    outputs = []
    for host in hosts:
        client = get_ssh(host)
        t = Thread(
            target=_ssh_exeute_thread,
            args=(client, command, allow_status, outputs))
        t.daemon = True
        ts.start()
    for t in ts:
        t.join()
    return outputs


def ssh_execute(client, command, allow_status=[0]):
    """Execute ssh blocking I/O

    We get allow_status as an input.
    We ignore some error status, if it exist in allow_status.

    :param client: SSHClient
    :param command: command
    :param allow_status: list of allow status.
    """
    try:
        logger.debug('[ssh_execute] %s' % command)
        stdin, stdout, stderr = client.exec_command(command)
    except Exception as e:
        print(e)
        raise e
    stdout_msg = ''
    stderr_msg = ''

    stdout_msg = stdout.read()
    stdout_msg = stdout_msg.decode('utf-8')
    if stdout_msg and stdout_msg is not "":
        logger.debug('---------------- command to : %s' % client.hostname)
        logger.debug(command)
        logger.debug('---------------- stdout')
        logger.debug(stdout_msg)

    stderr_msg = stderr.read()
    stderr_msg = stderr_msg.decode('utf-8')
    if stderr_msg and stderr_msg is not "":
        logger.debug('---------------- command to : %s' % client.hostname)
        logger.debug(command)
        logger.debug('---------------- stderr')
        logger.debug(stderr_msg)

    exit_status = stdout.channel.recv_exit_status()
    if exit_status not in allow_status:
        host = client.hostname
        stderr_msg = stderr_msg.encode('utf-8')
        raise SSHCommandError(exit_status, host, stderr_msg)
    return exit_status, stdout_msg, stderr_msg


def is_dir(client, file_path):
    """Determine if directory or not

    :param client: SSHClient
    :param file_path: absolute path of file
    """
    command = "[ -d '{}' ] && echo True || echo False".format(file_path)
    _, stdout, _ = ssh_execute(client, command)
    return stdout.strip() == 'True'


def is_exist(client, file_path):
    """Determine if exist or not

    :param client: SSHClient
    :param file_path: absolute path of file
    """
    command = "[ -e '{}' ] && echo True || echo False".format(file_path)
    _, stdout, _ = ssh_execute(client, command)
    return stdout.strip() == 'True'


def is_exist_files(client, file_path_list):
    """Determine if exist or not

    If there is not any single file, return false.

    :param client: SSHClient
    :param file_path_list: absolute path of file list
    """
    command = []
    for file_path in file_path_list:
        command.append("[ -e '{}' ] &&".format(file_path))
    command.append('echo True || echo False')
    command = ' '.join(command)
    _, stdout, _ = ssh_execute(client, command)
    return stdout.strip() == 'True'


def copy_dir_to_remote(client, local_path, remote_path):
    """copy directory from local to remote
    if already file exist, overwrite file
    copy all files recursively
    directory must exist

    :param client: SSHClient
    :param local_path: absolute path of file
    :param remote_path: absolute path of file
    """
    logger.debug('copy_dir_to_remote')
    logger.debug('copy FROM localhost:{} TO node:{}'.format(
        local_path,
        remote_path
    ))
    sftp = get_sftp(client)
    listdir = os.listdir(local_path)
    for f in listdir:
        r_path = os.path.join(remote_path, f)
        l_path = os.path.join(local_path, f)
        if os.path.isdir(l_path):
            if not is_exist(client, r_path):
                sftp.mkdir(r_path)
            copy_dir_to_remote(client, l_path, r_path)
        else:
            sftp.put(l_path, r_path)


def copy_dir_from_remote(client, remote_path, local_path):
    """copy directory from remote to local

    if already file exist, overwrite file
    copy all files recursively
    directory must exist

    :param client: SSHClient
    :param remote_path: absolute path of file
    :param local_path: absolute path of file
    """
    logger.debug('copy FROM node:{} TO localhost:{}'.format(
        remote_path,
        local_path
    ))
    sftp = get_sftp(client)
    listdir = sftp.listdir(remote_path)
    for f in listdir:
        r_path = os.path.join(remote_path, f)
        l_path = os.path.join(local_path, f)
        if is_dir(client, r_path):
            if not os.path.exists(l_path):
                os.mkdir(l_path)
            copy_dir_from_remote(client, r_path, l_path)
        else:
            sftp.get(r_path, l_path)


def get_home_path(host):
    client = get_ssh(host)
    command = 'echo $HOME'
    _, stdout, _ = ssh_execute(client, command)
    client.close()
    return stdout.strip()


def ping(host, duration=3):
    command = 'ping -c 1 -t {} {} > /dev/null 2>&1'.format(duration, host)
    response = os.system(command)
    print(response)
    logger.debug('ping to {}, respose: {}'.format(host, response))
    if response is not 0:
        raise HostConnectionError(host)


def is_port_empty(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = True
    status = 'OK'
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((host, port))
    except socket.error as e:
        result = False
        if e.errno == errno.EADDRINUSE:
            status = 'USED'
            logger.debug('{}:{} is already in use'.format(host, port))
        else:
            status = 'FAIL'
            logger.exception(e)
    except Exception as e:
        result = False
        status = 'FAIL'
        logger.exception(e)
    finally:
        return result, status


def get_ip(host):
    try:
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        raise HostNameError(host)
    return ip


def download_file(url, file_path):
    download_path = file_path + '.download'
    file_name = os.path.basename(file_path)
    try:
        with open(download_path, 'wb') as f:
            msg = message.get('file_download').format(file_name=file_name)
            logger.info(msg)
            logger.debug('url: {}'.format(url))
            logger.debug('installer name: {}'.format(file_name))
            response = requests.get(url, stream=True)
            response.raise_for_status()
            total_length = response.headers.get('content-length')
            if total_length is None:
                f.write(response.content)
            else:
                done_length = 0
                total_length = int(total_length)
                for data in response.iter_content(chunk_size=4096):
                    done_length += len(data)
                    f.write(data)
                    done = int(100 * done_length / total_length)
                    comp = '=' * int(done / 2)
                    remain = ' ' * int(50 - int(done / 2))
                    progress = '\r[{}{}] {}%'.format(comp, remain, done)
                    sys.stdout.write(progress)
                    sys.stdout.flush()
            print('')
            shutil.move(download_path, file_path)
            return True
    except requests.exceptions.HTTPError as ex:
        logger.warning(ex)
        return False
    except KeyboardInterrupt as ex:
        print('')
        raise ex
    except BaseException as ex:
        class_name = ex.__class__.__name__
        logger.warning('{}: {}'.format(class_name, url))
        return False
    finally:
        if os.path.isfile(download_path):
            os.remove(download_path)


def get_installers_from_fb_s3(maximum_number=5):
    '''bring up to maximum_number installers in the latest order from s3
    default value of maximum_value is 5
    if there is problem with url or network connection is fail,
    return empty list

    return
    [{
        name:string: file name
        url:string: download url
        type:string: url type
    }]
    '''
    ret = []
    url = 'https://flashbase.s3.ap-northeast-2.amazonaws.com/latest/latest.html'
    warning_msg = "Fail to load installer list from '{}'".format(url)
    try:
        res = requests.get(url)
        status_code = res.status_code
        if status_code >= 400:
            msg = message.get('error_http_request')
            msg = msg.format(code=status_code, msg=warning_msg)
            logger.warning(msg)
        res_text = str(res.text)
        res_text = list(map(lambda x: x.strip(), res_text.split('\n')))
        filtered = list(filter(lambda x: x.startswith('<a href='), res_text))
        for text in filtered:
            if maximum_number <= 0:
                break
            link = parser.get_word_between(text, '<a href="', '">')
            name = parser.get_word_between(text, '<a href=".*">', '/*</a>')
            ret.append({'name': name, 'url': link, 'type': 'download'})
            maximum_number -= 1
        return ret
    except requests.exceptions.ConnectionError:
        msg = message.get('error_http_connection').format(msg=warning_msg)
        logger.warning(msg)
        return []
