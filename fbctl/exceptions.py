class FbctlBaseError(Exception):
    '''base error for fbctl'''
    def __init__(self, message, *args):
        Exception.__init__(self, message, *args)
        self.message = message

    def __str__(self):
        return self.message

    def class_name(self):
        '''return class name'''
        return self.__class__.__name__


class FlashbaseError(FbctlBaseError):
    def __init__(self, error_code, message, *args):
        self.error_code = error_code
        FbctlBaseError.__init__(self, message, *args)


class ConvertError(FbctlBaseError):
    def __init__(self, message, *args):
        FbctlBaseError.__init__(self, message, *args)


class PropsKeyError(FbctlBaseError):
    def __init__(self, key, *args):
        message = "{} cannot empty in props".format(key.upper())
        FbctlBaseError.__init__(self, message, *args)


class PropsError(FbctlBaseError):
    def __init__(self, message, *args):
        FbctlBaseError.__init__(self, message, *args)


class FileNotExistError(FbctlBaseError):
    def __init__(self, file_path, **kwargs):
        message = "'{}'".format(file_path)
        if 'host' in kwargs.keys():
            self.host = kwargs['host']
            message = "'{}' at '{}'".format(file_path, self.host)
        FbctlBaseError.__init__(self, message, *kwargs)


class SSHConnectionError(FbctlBaseError):
    def __init__(self, host, *args):
        message = "SSH connection fail to '{}'".format(host)
        FbctlBaseError.__init__(self, message, *args)


class HostConnectionError(FbctlBaseError):
    def __init__(self, host, *args):
        message = "Host connection fail to '{}'".format(host)
        FbctlBaseError.__init__(self, message, *args)


class HostNameError(FbctlBaseError):
    def __init__(self, host, *args):
        message = "Unknown host name '{}'".format(host)
        FbctlBaseError.__init__(self, message, *args)


class YamlSyntaxError(FbctlBaseError):
    def __init__(self, file_path, *args):
        FbctlBaseError.__init__(self, "'{}'".format(file_path), *args)


class PropsSyntaxError(FbctlBaseError):
    def __init__(self, line, line_number, *args):
        message = "'{}' at line {}".format(line, line_number)
        FbctlBaseError.__init__(self, message, *args)


class ClusterIdError(FbctlBaseError):
    def __init__(self, cluster_id, *args):
        message = "Invalid cluster id '{}'".format(cluster_id)
        FbctlBaseError.__init__(self, message, *args)


class ClusterNotExistError(FbctlBaseError):
    def __init__(self, cluster_id, **kwargs):
        message = "Not exist cluster '{}'".format(cluster_id)
        if 'host' in kwargs.keys():
            self.host = kwargs['host']
            message = "{} at '{}'".format(message, self.host)
        FbctlBaseError.__init__(self, message, *kwargs)


class ClusterRedisError(FbctlBaseError):
    def __init__(self, message, *args):
        FbctlBaseError.__init__(self, message, *args)


class SSHCommandError(FbctlBaseError):
    def __init__(self, exit_status, host, stderr, *args):
        self.exit_status = exit_status
        self.host = host
        self.stderr = stderr
        message = "[ExitCode {}] Fail execute command at '{}': {}".format(
            exit_status,
            host,
            stderr
        )
        FbctlBaseError.__init__(self, message, *args)


class CreateDirError(FbctlBaseError):
    def __init__(self, message, dir_path, *args):
        self.dir_path = dir_path
        FbctlBaseError.__init__(self, message, *args)


class EnvError(FbctlBaseError):
    def __init__(self, env, *args):
        message = 'you should set env {}'.format(env)
        FbctlBaseError.__init__(self, message, *args)
