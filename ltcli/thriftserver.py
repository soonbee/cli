import subprocess as sp
import os
import re
import time

from ltcli import config, message
from ltcli.log import logger
from ltcli.exceptions import FileNotExistError, EnvError


# pylint: disable=line-too-long, anomalous-backslash-in-string
ROLLING_LOGFILE_REGEX = 'spark.*rolling.*org\.apache\.spark\.sql\.hive\.thriftserver\.HiveThriftServer2-1.*\.log'
NOHUP_LOGFILE_REGEX = 'spark.*org\.apache\.spark\.sql\.hive\.thriftserver\.HiveThriftServer2-1.*\.out'
ROLLING_LOGFILE = 'spark*rolling*org.apache.spark.sql.hive.thriftserver.HiveThriftServer2-1*.log'
NOHUP_LOGFILE = 'spark*org.apache.spark.sql.hive.thriftserver.HiveThriftServer2-1*.out'


def _get_env():
    if 'SPARK_HOME' not in os.environ:
        raise EnvError('you should set env SPARK_HOME')
    ret = {
        'spark_home': os.environ['SPARK_HOME'],
    }
    env_list = ['SPARK_BIN', 'SPARK_SBIN', 'SPARK_LOG', 'SPARK_CONF']
    cluster_id = config.get_cur_cluster_id()
    path_of_fb = config.get_path_of_fb(cluster_id)
    ths_props_path = path_of_fb['thrift_properties']
    for env in env_list:
        cmd = 'source {}; echo ${}'.format(ths_props_path, env.upper())
        stdout = sp.check_output(cmd, shell=True).decode('utf-8').strip()
        ret[env.lower()] = stdout
    return ret


def _check_spark():
    spark_env = _get_env()
    if not os.path.isdir(spark_env['spark_home']):
        raise FileNotExistError(spark_env['spark_home'])
    if not os.path.isdir(spark_env['spark_bin']):
        raise FileNotExistError(spark_env['spark_bin'])
    if not os.path.isdir(spark_env['spark_sbin']):
        raise FileNotExistError(spark_env['spark_sbin'])


def _get_hive_opts_str():
    ret = [
        '--hiveconf hive.server2.thrift.bind.host=$HIVE_HOST \\',
        '--hiveconf hive.server2.thrift.port=$HIVE_PORT \\',
        '--master yarn \\',
        '--executor-memory $EXECUTOR_MEMORY \\',
        '--driver-memory $DRIVER_MEMORY \\',
        '--num-executors $EXECUTERS \\',
        '--conf spark.ui.port=$SPARK_UI_PORT \\',
        '--conf spark.metrics.conf=$SPARK_METRICS \\',
        '--conf spark.executor.cores=$EXECUTER_CORES \\',
        '--conf spark.executor.extraClassPath=$EXECUTOR_CLASSPATH \\',
        '--driver-class-path $DRIVER_CLASSPATH \\',
        '--conf spark.eventLog.enabled=$EVENT_LOG_ENABLED \\',
        '--conf spark.eventLog.dir=$EVENT_LOG_DIR \\',
    ]
    return '\n'.join(ret)


def _find_files_with_regex(dir_path, pattern):
    ret = []
    for filename in os.listdir(dir_path):
        if re.search(pattern, filename):
            ret.append(filename)
    return ret


class ThriftServer(object):
    """Thriftserver command
    """

    def beeline(self, **kargs):
        """Connect to thriftserver command line
        """
        logger.debug('thriftserver_command_beeline')
        _check_spark()
        cluster_id = config.get_cur_cluster_id()
        path_of_fb = config.get_path_of_fb(cluster_id)
        ths_props_path = path_of_fb['thrift_properties']
        cmd = 'source {}; echo ${}'.format(ths_props_path, 'HIVE_HOST')
        host = sp.check_output(cmd, shell=True).decode('utf-8').strip()
        cmd = 'source {}; echo ${}'.format(ths_props_path, 'HIVE_PORT')
        port = sp.check_output(cmd, shell=True).decode('utf-8').strip()
        spark_env = _get_env()
        base_cmd = '{}/beeline'.format(spark_env['spark_bin'])
        options = {
            'u': 'jdbc:hive2://{}:{}'.format(host, port),
            'n': os.environ['USER']
        }
        for key, value in kargs.items():
            options[key] = value
        for key, value in options.items():
            base_cmd += ' -{} {}'.format(key, value)
        logger.debug(base_cmd)
        msg = message.get('try_connection')
        logger.info(msg)
        os.system(base_cmd)

    def start(self):
        """Start thriftserver
        """
        logger.debug('thriftserver_command_start')
        _check_spark()
        cluster_id = config.get_cur_cluster_id()
        path_of_fb = config.get_path_of_fb(cluster_id)
        ths_props_path = path_of_fb['thrift_properties']
        source_cmd = 'source {}'.format(ths_props_path)
        hive_opts = _get_hive_opts_str()
        base_cmd = '$SPARK_SBIN/start-thriftserver.sh {}'.format(hive_opts)
        cmd = '{}; {}'.format(source_cmd, base_cmd)
        logger.debug(cmd)
        os.system(cmd)
        spark_log = os.path.join(os.environ['SPARK_HOME'], 'logs')
        if _find_files_with_regex(spark_log, ROLLING_LOGFILE_REGEX):
            for file in _find_files_with_regex(spark_log, NOHUP_LOGFILE_REGEX):
                os.remove(os.path.join(spark_log, file))

    def stop(self):
        """Stop thriftserver
        """
        logger.debug('thriftserver_command_stop')
        _check_spark()
        cluster_id = config.get_cur_cluster_id()
        path_of_fb = config.get_path_of_fb(cluster_id)
        ths_props_path = path_of_fb['thrift_properties']
        source_cmd = 'source {}'.format(ths_props_path)
        base_cmd = '$SPARK_SBIN/stop-thriftserver.sh'
        cmd = '{}; {}'.format(source_cmd, base_cmd)
        logger.debug(cmd)
        os.system(cmd)

    def monitor(self):
        """Monitoring log of thriftserver"
        """
        logger.debug('thriftserver_command_monitor')
        _check_spark()
        cluster_id = config.get_cur_cluster_id()
        path_of_fb = config.get_path_of_fb(cluster_id)
        ths_props_path = path_of_fb['thrift_properties']
        source_cmd = 'source {}'.format(ths_props_path)
        spark_log = _get_env()['spark_log']
        # log_file_path = ''.join([
        #     spark_log,
        #     '/spark-{}-org.apache'.format(os.environ['USER']),
        #     '.spark.sql.hive.thriftserver.HiveThriftServer2-1-*.out',
        # ])
        log_file_path = os.path.join(spark_log, NOHUP_LOGFILE)
        if _find_files_with_regex(spark_log, ROLLING_LOGFILE_REGEX):
            log_file_path = os.path.join(spark_log, ROLLING_LOGFILE)
        base_cmd = 'tail -F {}'.format(log_file_path)
        cmd = '{}; {}'.format(source_cmd, base_cmd)
        logger.debug(cmd)
        msg = message.get('message_for_exit')
        logger.info(msg)
        os.system(cmd)

    def restart(self):
        """Restart thriftserver
        """
        self.stop()
        time.sleep(2)
        self.start()
