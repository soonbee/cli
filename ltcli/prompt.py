from os import environ

from ltcli import config


def get_cli_prompt():
    """Return cli prompt

    :param user: user name
    :return: prompt string
    """
    cluster_id = config.get_cur_cluster_id(allow_empty_id=True)
    if cluster_id < 0:
        cluster_id = '-'
    user = environ['USER']
    prompt_classname = u'class:ansiwhite'
    prompt_message = u'{}@lightningdb:{}> '.format(user, cluster_id)
    return [(prompt_classname, prompt_message)]


def get_sql_prompt():
    """Return sql prompt

    :param user: user name
    :return: prompt string
    """
    cluster_id = config.get_cur_cluster_id(allow_empty_id=True)
    if cluster_id < 0:
        cluster_id = '-'
    user = environ['USER']
    prompt_classname = u'class:ansigreen'
    prompt_message = u'({}){}@lightningdb:sql> '.format(cluster_id, user)
    return [(prompt_classname, prompt_message)]
