class LtcliBaseError(Exception):
    '''base error for ltcli'''
    def __init__(self, message, *args):
        Exception.__init__(self, message, *args)
        self.message = message

    def __str__(self):
        return self.message

    def class_name(self):
        '''return class name'''
        return self.__class__.__name__


class LightningDBError(LtcliBaseError):
    def __init__(self, error_code, message, *args):
        self.error_code = error_code
        LtcliBaseError.__init__(self, message, *args)


class ConvertError(LtcliBaseError):
    def __init__(self, message, *args):
        LtcliBaseError.__init__(self, message, *args)


class PropsKeyError(LtcliBaseError):
    def __init__(self, key, *args):
        message = "{} cannot empty in props".format(key.upper())
        LtcliBaseError.__init__(self, message, *args)


class PropsError(LtcliBaseError):
    def __init__(self, message, *args):
        LtcliBaseError.__init__(self, message, *args)


class FileNotExistError(LtcliBaseError):
    def __init__(self, file_path, **kwargs):
        message = "'{}'".format(file_path)
        if 'host' in kwargs.keys():
            self.host = kwargs['host']
            message = "'{}' at '{}'".format(file_path, self.host)
        LtcliBaseError.__init__(self, message, *kwargs)


class SSHConnectionError(LtcliBaseError):
    def __init__(self, host, *args):
        message = "SSH connection fail to '{}'".format(host)
        LtcliBaseError.__init__(self, message, *args)


class HostConnectionError(LtcliBaseError):
    def __init__(self, host, *args):
        message = "Host connection fail to '{}'".format(host)
        LtcliBaseError.__init__(self, message, *args)


class HostNameError(LtcliBaseError):
    def __init__(self, host, *args):
        message = "Unknown host name '{}'".format(host)
        LtcliBaseError.__init__(self, message, *args)


class YamlSyntaxError(LtcliBaseError):
    def __init__(self, file_path, *args):
        LtcliBaseError.__init__(self, "'{}'".format(file_path), *args)


class PropsSyntaxError(LtcliBaseError):
    def __init__(self, line, line_number, *args):
        message = "'{}' at line {}".format(line, line_number)
        LtcliBaseError.__init__(self, message, *args)


class ClusterIdError(LtcliBaseError):
    def __init__(self, cluster_id, *args):
        message = "Invalid cluster id '{}'".format(cluster_id)
        LtcliBaseError.__init__(self, message, *args)


class ClusterNotExistError(LtcliBaseError):
    def __init__(self, cluster_id, **kwargs):
        message = "Not exist cluster '{}'".format(cluster_id)
        if 'host' in kwargs.keys():
            self.host = kwargs['host']
            message = "{} at '{}'".format(message, self.host)
        LtcliBaseError.__init__(self, message, *kwargs)


class ClusterRedisError(LtcliBaseError):
    def __init__(self, message, *args):
        LtcliBaseError.__init__(self, message, *args)


class SSHCommandError(LtcliBaseError):
    def __init__(self, exit_status, host, stderr, *args):
        self.exit_status = exit_status
        self.host = host
        self.stderr = stderr
        message = "[ExitCode {}] Fail execute command at '{}': {}".format(
            exit_status,
            host,
            stderr
        )
        LtcliBaseError.__init__(self, message, *args)


class CreateDirError(LtcliBaseError):
    def __init__(self, message, dir_path, *args):
        self.dir_path = dir_path
        LtcliBaseError.__init__(self, message, *args)


class EnvError(LtcliBaseError):
    def __init__(self, env, *args):
        message = 'you should set env {}'.format(env)
        LtcliBaseError.__init__(self, message, *args)
