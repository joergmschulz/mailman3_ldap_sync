# Mailman3 LDAP Sync

Synchronizing mailman3 list against ldap with ease. has been tested for OpenLDAP and Active Directory.

Features:
- dockerized version
- Search through DN if group member is a DN record (Active Directory)
- Adding some prefix in list name
- Hooks, module that will be executed in the end of script
- Excluding list for being deleted by regex pattern


## Installing

- Clone repository
```sh
git clone 
```
- edit .env, config.ini, docker-compose.yml
- start 
## Logrotate

If you are enabling script log file and run script scheduled (using crontab) then you may set log rotation for not make it's bigger time by time.

**/etc/logrotate.d/mailman3_ldapsync**
```
/var/log/mailman3_ldapsync.log {
    daily
    missingok
    notifempty
    create 0644 1000 1000
    compress
}
```

## Using the Script


```
docker compose run --rm mm3_sync python m3_sync.py /etc/mm3sync.ini
```

before first start
```
sudo touch /data/freie-dorfschule/mm3sync/log/mailman3_ldapsync.log && sudo chown -R 1000:1000 /data/freie-dorfschule/mm3sync/log/mailman3_ldapsync.log
```

## DMARC
To send mails to certain providers, you need to munge/masquerade for certain domains. See docker-compose.yml and https://docs.mailman3.org/projects/mailman/en/latest/src/mailman/handlers/docs/dmarc-mitigations.html

## Develop
if you set DEBUG_DEVELOP=true, the pdb debugger is started.

