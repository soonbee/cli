import os
import shutil


from fbctl import config
from fbctl.log import logger
from fbctl import editor
from fbctl.center import Center
from fbctl import ask_util


class Conf(object):
    """command for edit conf file.

    open conf file with editor.
    sync to all hosts after edit.
    """
    def __init__(self):
        pass

    def cluster(self):
        """edit 'redis.properties' of cluster
        """
        cluster_id = config.get_cur_cluster_id()
        path_of_fb = config.get_path_of_fb(cluster_id)
        target_path = path_of_fb['redis_properties']
        self._edit_conf(target_path, syntax='sh')
        center = Center()
        center.update_ip_port()
        success = center.check_hosts_connection()
        if not success:
            return
        success = center.sync_file(target_path)
        if success:
            logger.info('Complete edit')

    def master(self):
        """ edit 'redis-master.conf.template'
        """
        cluster_id = config.get_cur_cluster_id()
        path_of_fb = config.get_path_of_fb(cluster_id)
        target_path = path_of_fb['master_template']
        self._edit_conf(target_path, syntax='sh')
        center = Center()
        center.update_ip_port()
        success = center.check_hosts_connection()
        if not success:
            return
        success = center.sync_file(target_path)
        if success:
            logger.info('Complete edit')

    def slave(self):
        """edit 'redis-slave.conf.template'
        """
        cluster_id = config.get_cur_cluster_id()
        path_of_fb = config.get_path_of_fb(cluster_id)
        target_path = path_of_fb['slave_template']
        self._edit_conf(target_path, syntax='sh')
        center = Center()
        center.update_ip_port()
        success = center.check_hosts_connection()
        if not success:
            return
        success = center.sync_file(target_path)
        if success:
            logger.info('Complete edit')

    def thriftserver(self):
        """edit 'thriftserver.properties'
        """
        cluster_id = config.get_cur_cluster_id()
        path_of_fb = config.get_path_of_fb(cluster_id)
        target_path = path_of_fb['thrift_properties']
        self._edit_conf(target_path, syntax='sh')
        center = Center()
        center.update_ip_port()
        success = center.check_hosts_connection()
        if not success:
            return
        success = center.sync_file(target_path)
        if success:
            logger.info('Complete edit')

    def ths(self):
        """alias of thriftserver
        """
        self.thriftserver()

    def _edit_conf(self, target_path, syntax=None):
        tmp_target_path = target_path + '.tmp'
        if os.path.exists(tmp_target_path):
            q = 'There is a history of modification. Do you want to load?'
            yes = ask_util.askBool(q)
            if not yes:
                os.remove(tmp_target_path)
        if not os.path.exists(tmp_target_path):
            shutil.copy(target_path, tmp_target_path)
        editor.edit(tmp_target_path, syntax=syntax)
        shutil.copy(tmp_target_path, target_path)
        os.remove(tmp_target_path)
