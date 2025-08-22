#!/usr/bin/env python3

__author__ = ('Imam Omar Mochtar, amended by Joerg M. Schulz')
__email__ = ('iomarmochtar@gmail.com',)
__version__ = "1.0"
__license__ = "GPL"

import os
import sys
import re
import logging
import traceback
from pprint import pprint
from mailmanclient import Client as Mailman3Client
from colorlog import ColoredFormatter
from six.moves.urllib_error import HTTPError
from ldap3 import Server, Connection, ALL, ALL_ATTRIBUTES, BASE
try:
    from ConfigParser import ConfigParser
except ImportError:
    # for python 3
    from configparser import ConfigParser

if os.environ.get('DEBUG_DEVELOP') == 'true':
	import pdb
class M3Sync(object):

    __attrs = ['subscriber', 'owner', 'moderator']
    logger = logging.getLogger('Mailman3Sync')

    def __init__(self, config):
        
        self.sync = dict(config.items('sync'))
        # add environment variables (later we'll completely switch to env)
        for k in self.sync:
            if 'os.environ.get' in self.sync[k]:
                self.sync[k]=eval(self.sync[k])
        self.config = config

        self.init_logger()
        self.init_hooks()
        self.init_mailman3api()
        self.init_ldap()

    def init_hooks(self):
        """
        Initialize hooks, for any module that will be executed after sync was done
        """
        conf = dict(self.config.items('hooks'))
        self.hooks = []
        for hook, module_name in conf.items():
            self.hooks.append({
                'name': hook,
                'module': getattr(__import__("hooks.{0}".format(module_name)), module_name),
                'conf': {} if not self.config.has_section(hook) else dict(self.config.items(hook))
            })

    def init_ldap(self):
        """
        Initialize ldap connection
        """
        conf = dict(self.config.items('ldap'))
        for k in conf:
            if 'os.environ.get' in conf[k]:
                conf[k]=eval(conf[k])
        self.ldap = Connection(
            Server(conf['host'], get_info=ALL),
            conf['bind_dn'], conf['bind_pwd'], auto_bind=True
        )

    def init_mailman3api(self):
        """
        Initialize mailman3 API
        """
        # set conf api
        conf = dict(self.config.items('mailman3'))
        for k in conf:
            if 'os.environ.get' in conf[k]:
                conf[k]=eval(conf[k])
        
        self.m3 = Mailman3Client(
            'http://{0}:{1}/{2}'.format(conf['host'], conf['port'], conf['mm3api_version']),
            conf['user'], conf['pwd']
        )
        try:
            self.m3.system
        except Exception:
            msg = traceback.format_exc(limit=1)
            self.logger.error(
                "Error while connecting to conf api: {0}".format(msg))

    def init_logger(self):
        """
        Initiate log console & file (if enabled)
        """
        formatter = ColoredFormatter(
            "%(yellow)s%(asctime)s %(reset)s- %(log_color)s%(levelname)-8s%(reset)s - %(blue)s%(message)s",
            reset=True,
            log_colors={
                'DEBUG': 'cyan',
                'INFO':	'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'blue',
            }
        )

        log_lvl = logging.DEBUG

        handler = logging.StreamHandler()
        handler.setFormatter(formatter)

        self.logger.addHandler(handler)
        self.logger.setLevel(log_lvl)

        if 'log_file' in self.sync and self.sync['log_file']:
            fh = logging.FileHandler(self.sync['log_file'], 'a')
            fh.setLevel(log_lvl)
            fh.setFormatter(
                logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            )
            self.logger.addHandler(fh)

    def get_list_byname(self, domain, list_name):
        """
        a wrapper for get list by name
        """
        for mlist in domain.lists:
            if mlist.list_name != list_name:
                continue
            return mlist
        return None

    def get_list(self, name):
        """
        get list with additional prefix if enabled
        """
        prefix = self.sync['list_prefix']
        # lowercased
        name = name.lower()
        if not prefix:
            return name
        return "{0}{1}".format(prefix, name)

    def exec_hooks(self, ldap_data):
        """
        Running all available hooks
        """
        for hook in self.hooks:
            name = hook['name']
            self.logger.info("Executing hook {0}".format(name))
            result = hook['module'].main(
                conf=hook['conf'],
                instance=self,
                data=ldap_data
            )
            if result:
                self.logger.info(
                    "Result of hoook {0} is {1}".format(name, result))

    def set_settings(self, mlist):
        mlist.settings['send_welcome_message'] = False
        mlist.settings['max_message_size'] = 0
        mlist.settings['advertised'] = False
        mlist.settings['subscription_policy'] = "confirm_then_moderate"
        mlist.settings['archive_policy'] = "never"
        mlist.settings['preferred_language'] = self.sync['preferred_language']
        mlist.settings.save()
     
    def main(self):
        # find group
        ret_attr = [
            self.sync['group_name_attr'], self.sync['subscriber_attr'], 
            self.sync['owner_attr'], self.sync['moderator_attr'], "cn", "description", self.sync['listmail_attr']
        ]
        search_result = self.ldap.search(
            self.sync['search_base'],
            self.sync['group_filter'],
            attributes=ret_attr
        )
        
        # regex was taken from http://emailregex.com/
        email_re = re.compile(
            r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)")

        ldap_data = {}
        for group in self.ldap.entries:
            # change all space to dot for group name
            list_name = str(group["cn"])
            ldap_data[self.get_list(list_name)] = dict(
                zip(self.__attrs, [[] for x in range(len(self.__attrs))])
            )
            ldap_data[self.get_list(list_name)]['description'] =  str(group["description"])
            ldap_data[self.get_list(list_name)]['mail'] =  group["mail"][0] if len(group["mail"])>0 else ''

            for attr in self.__attrs:
                for dn in getattr(group, self.sync['{0}_attr'.format(attr)]):
                    # if it's not email form then search by it's DN. this is used if quering group member agains AD
                    
                    email = None
                    if email_re.search(dn):
                        email = dn
                    else:
                        self.ldap.search(
                            dn,
                            self.sync['member_filter'],
                            attributes=[self.sync['mail_attr']],
                            search_scope=BASE
                        )
                        if len(self.ldap.entries) != 0:
                            email = getattr(
                                self.ldap.entries[0], self.sync['mail_attr']).value

                    if not email:
                        self.logger.warning('LDAP data for {}, is not an email or it doesn\'t has email attribute'.format(dn))
                        continue

                    if 'replace_mail_domain' in self.sync and self.sync['replace_mail_domain']:
                        email = re.sub(r'@.*?$', '@{}'.format(self.sync['replace_mail_domain']), email)

                    # lower case the email
                    ldap_data[self.get_list(list_name)][attr].append(
                        email.lower())

        # make sure default domain exist
        self.logger.info('Creating default list domain: {0}'.format(
            self.sync['default_list_domain']))
        try:
            self.m3.create_domain(self.sync['default_list_domain'])
        except HTTPError:
            self.logger.warning('domain {0} already exist'.format(
                self.sync['default_list_domain']))
        

        domain = self.m3.get_domain(self.sync['default_list_domain'])

        # LDAP -> MAILMAN add data to mailman
        for list_name, datas in ldap_data.items():
            # Create List
            self.logger.info("Create list {0} in domain {1}".format(
                list_name, self.sync['default_list_domain']))
            try:
                # create list by listname or by email address
                mlist = domain.create_list( datas['mail'].replace( '@'+str(domain), '') if 'mail' in datas and len(str(datas['mail']))>0 else list_name)
                self.set_settings(mlist)
            except HTTPError as e:
                print(e)
                self.logger.warning(
                    "List with name {0} already exists".format(list_name))
                mlist = self.get_list_byname(domain, list_name)
                if mlist == None:
                    self.logger.warning("Failed to add list {0}".format(list_name))
                    continue

            mlist_name = mlist.fqdn_listname # important to use this and not the list name

            # add domain as accepted non-member
            if '@' in self.sync['accept_nonmembers'] :
                mlist.settings['accept_these_nonmembers'] = [self.sync['accept_nonmembers']]
            else:
                mlist.settings['accept_these_nonmembers'] = []
            
                    
            mlist.settings['dmarc_addresses'] = eval(os.environ.get('MM3_DMARC_ADDRESSES')) if os.environ.get('MM3_DMARC_ADDRESSES') else []
            mlist.settings['dmarc_mitigate_action'] = os.environ.get('MM3_DMARC_ACTION' ) if os.environ.get('MM3_DMARC_ACTION') else no_mitigation
            # add description
            mlist.settings['description'] = datas['description']
            mlist.settings['display_name'] = list_name
            mlist.settings.save()

            # subscriber
            for subscriber in datas['subscriber']:
                try:
                    self.logger.info("Add subscriber {0} to list {1}".format(
                        subscriber, mlist_name))
                    mlist.subscribe(subscriber, pre_verified=True,
                                    pre_confirmed=True, pre_approved=True)
                except HTTPError:
                    self.logger.warning("subscriber {0} already exist in {1}".format(
                        subscriber, mlist_name))

            # moderator
            for moderator in datas['moderator']:
                try:
                    self.logger.info(
                        "Add moderator {0} to list {1}".format(moderator, mlist_name))
                    mlist.add_moderator(moderator)
                except HTTPError:
                    self.logger.warning(
                        "moderator {0} already exist in {1}".format(moderator, mlist_name))
                try:
                    self.logger.info("Add moderator {0} subscriber to list {1}".format(
                        moderator, mlist_name))
                    mlist.subscribe(moderator, pre_verified=True,
                                    pre_confirmed=True, pre_approved=True)
                except HTTPError:
                    self.logger.warning("moderator {0} already exist in {1}".format(
                        moderator, mlist_name))

            # owner
            for owner in datas['owner']:
                try:
                    self.logger.info(
                        "Add owner {0} to list {1}".format(owner, mlist_name))
                    mlist.add_owner(owner)
                except HTTPError:
                    self.logger.warning(
                        "owner {0} already exist in {1}".format(moderator, mlist_name))
            mlist.settings.save()


        # MAILMAN -> LDAP, check for diff then remove when it not exist
        # comparing member, if doesn't exist in ldap data then delete them
        for mlist in domain.lists:
            list_name = mlist.display_name # not list_name
            # delete the rest of list if doesn't exist in ldap


            if list_name not in ldap_data.keys():
                if self.sync['delete_rest_list'] == 'true':
                    # some are excluded using regex pattern
                    if self.sync['exclude_list_re'] and re.search(r'{0}'.format(self.sync['exclude_list_re']), mlist.list_name):
                        continue

                    self.logger.info(
                        "Deleting list {0}".format(mlist.fqdn_listname))
                    mlist.delete()

                continue
            
            self.set_settings(mlist)

            for member in mlist.members:
                if member.email not in ldap_data[list_name]['subscriber'] and member.email not in ldap_data[list_name]['moderator']:
                    self.logger.info("Unsubscribe {0} from list {1}".format(
                        member.email, list_name))
                    member.unsubscribe()
            

            for moderator in mlist.moderators:
                
                if moderator.address.email not in ldap_data[list_name]['moderator']:
                    self.logger.info(
                        "Removing moderator {0} from list {1}".format(moderator, list_name))
                    if os.environ.get('DEBUG_DEVELOP') == 'true':
                        pdb.set_trace()
                    mlist.remove_moderator(moderator)

            for owner in mlist.owners:
                if owner.address.email not in ldap_data[list_name]['owner']:
                    self.logger.info(
                        "Removing owner {0} from list {1}".format(owner, list_name))
                    mlist.remove_owner(owner)
            mlist.settings.save()


        self.exec_hooks(ldap_data)


if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    options = sys.argv
    # MAIN_CONF = os.path.join(BASE_DIR, 'config.ini')
    MAIN_CONF = options[1]
    if not os.path.isfile(MAIN_CONF):
        logExit("main configuration not found")

    parser = ConfigParser()
    parser.read(MAIN_CONF)

    M3Sync(
        config=parser
    ).main()
