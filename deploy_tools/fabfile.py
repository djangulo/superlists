import os
import random
from fabric.api import env, local, run, sudo, put, settings
from fabric.contrib.files import append, exists, sed

REPO_URL = 'https://github.com/djangulo/superlists.git'
# env['sudo_user'] = 'djangulo'
env.password = env.get('sudo_password')
project_name = env.get('project_name', None)
default = env.get('default', False)
media = env.get('media', False)
ssl = env.get('ssl', False)
static = env.get('static', False)
c_max = env.get('client_max', 10)

def deploy():
    site_folder = f'/home/{env.user}/sites/{env.host}'
    source_folder = site_folder + '/source'
    _install_necessary_packages()
    _create_directory_structure_if_necessary(site_folder)
    _get_latest_source(source_folder)
    _update_settings(source_folder, env.host, setup_media=media)
    _update_virtualenv(source_folder)
    _update_static_files(source_folder)
    _update_database(source_folder)
    _install_gunicorn_systemd_service(env.host)
    _configure_nginx(env.host,  is_default_server=default, setup_media=media,
                    setup_static=static, client_max=c_max)
    _nginx_check_and_restart()
    if ssl == 'True':
        _configure_nginx(env.host, setup_le=ssl)
        _nginx_check_and_restart()
        _letsencrypt_get_cert(env.host, user_email='denis.angulo@linekode.com')
        _configure_nginx(env.host, ssl_redirect=ssl)
        _nginx_check_and_restart()

def co_deploy():
    _configure_nginx(env.host,  is_default_server=default, setup_media=media,
                    setup_static=static, ssl_redirect=ssl, client_max=c_max)

def _install_necessary_packages():
    sudo(
        'add-apt-repository -y ppa:fkrull/deadsnakes'
        ' && apt-get -y update'
        ' && apt-get install -y nginx git python3.6 python3.6-venv'
    )

def _create_directory_structure_if_necessary(site_folder):
    for subfolder in ('database', 'static', 'virtualenv', 'source', 'media'):
        run(f'mkdir -p {site_folder}/{subfolder}')

def _get_latest_source(source_folder):
    if exists(source_folder + '/.git'):
        run(f'cd {source_folder} && git fetch')
    else:
        run(f'git clone {REPO_URL} {source_folder}')
    current_commit = local("git log -n 1 --format=%H", capture=True)
    run(f'cd {source_folder} && git reset --hard {current_commit}')

def _update_settings(source_folder, site_name, setup_media=False):
    settings_path = f'{source_folder}/{project_name}/settings.py'
    sed(settings_path, "DEBUG = True", "DEBUG = False")
    sed(
        settings_path,
        'ALLOWED_HOSTS = .+$',
        f'ALLOWED_HOSTS = ["{site_name}"]'
    )
    secret_key_file = f'{source_folder}/{project_name}/secret_key.py'
    if not exists(secret_key_file):
        chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
        key = ''.join(random.SystemRandom().choice(chars) for _ in range(50))
        append(secret_key_file, f'SECRET_KEY = "{key}"')
    append(settings_path, '\nfrom .secret_key import SECRET_KEY')
    if setup_media:
        with settings(warn_only=True):
            root_check = run(f'grep MEDIA_ROOT {source_folder}/{project_name}/settings.py')
            if root_check.failed:
                run("""echo "\nMEDIA_ROOT = os.path.abspath(os.path.join(BASE_DIR, '../media'))" """
                    f'| tee -a {source_folder}/{project_name}/settings.py')
            url_check = run(f'grep MEDIA_URL {source_folder}/{project_name}/settings.py')
            if url_check.failed:
                run("""echo "\nMEDIA_URL = '/media/'" """
                    f'| tee -a {source_folder}/{project_name}/settings.py')

def _install_gunicorn_systemd_service(site_name):
    if not exists(f'/etc/systemd/system/gunicorn-{site_name}.service'):
        put('gunicorn-systemd.template.service',
            f'/home/{env.user}/gunicorn-{site_name}.service')
        sed(f'/home/{env.user}/gunicorn-{site_name}.service',
            'SITENAME', f'{site_name}')
        sed(f'/home/{env.user}/gunicorn-{site_name}.service',
            'USERNAME', f'{env.user}')
        sudo(f'mv /home/{env.user}/gunicorn-{site_name}.service'
            f' /etc/systemd/system/gunicorn-{site_name}.service')
    sudo('systemctl daemon-reload')
    sudo(f'systemctl enable gunicorn-{site_name}')
    sudo(f'systemctl start gunicorn-{site_name}')
    sudo(f'systemctl restart gunicorn-{site_name}')

def _update_virtualenv(source_folder):
    virtualenv_folder = source_folder + '/../virtualenv'
    if not exists(virtualenv_folder + '/bin/pip'):  
        run(f'python3.6 -m venv {virtualenv_folder}')
    run(f'{virtualenv_folder}/bin/pip install -r {source_folder}/requirements.txt')

def _update_static_files(source_folder):
    run(
        f'cd {source_folder}'  
        ' && ../virtualenv/bin/python manage.py collectstatic --noinput'  
    )

def _update_database(source_folder):
    run(
        f'cd {source_folder}'
        ' && ../virtualenv/bin/python manage.py migrate --noinput'
    )

def _configure_nginx(
    site_name, is_default_server=False, setup_media=False,
    setup_static=False, setup_le=False, ssl_redirect=False, client_max=10):
    default_server = ' default_server;' if is_default_server == 'True' else ';'
    nginx_av = f'/etc/nginx/sites-available/{site_name}.nginx.conf'
    nginx_en = f'/etc/nginx/sites-enabled/{site_name}.nginx.conf'
    if not exists(nginx_av):
        put('gunicorn-nginx.template.conf', f'/home/{env.user}/{site_name}.nginx.conf')
        sudo(f'mv /home/{env.user}/{site_name}.nginx.conf'
            f' {nginx_av}')
        sudo(f'sed -i s/SITENAME/{site_name}/g'
            f' {nginx_av}')
        sudo(f'sed -i s/USERNAME/{env.user}/g'
            f' {nginx_av}')
        
    if is_default_server == 'True':
        sudo(f"sed -i 's/listen 80;/listen 80{default_server}/g'"
            f' {nginx_av}')
        sudo(f"sed -i 's/listen [::]:80;/listen [::]:80{default_server}/g'"
            f' {nginx_av}')
    if ssl_redirect == 'True':
        if not exists(f'/etc/nginx/snippets/ssl-{site_name}.conf'):
            put('ssl-template.conf', f'/home/{env.user}/ssl-{site_name}.conf')
            sed(
                f'/home/{env.user}/ssl-{site_name}.conf',
                'SITENAME',
                f'{site_name}'
            )
            sudo(f'mv /home/{env.user}/ssl-{site_name}.conf'
                f' /etc/nginx/snippets/ssl-{site_name}.conf')
        if not exists(f'/etc/nginx/snippets/ssl-params.conf'):
            put('ssl-params.conf', f'/home/{env.user}/ssl-params.conf')
            sudo(f'mv /home/{env.user}/ssl-params.conf'
                ' /etc/nginx/snippets/ssl-params.conf')
        if not exists('/etc/ssl/certs/dhparam.pem'):
            sudo('openssl dhparam -out /etc/ssl/certs/dhparam.pem 4096')

        with settings(warn_only=True):
            ssl_check = run(f"grep 'listen 443' {nginx_av}").failed
        if ssl_check:
            sudo(r"sed -i '/#LE-PLACEHOLDER#/a\    }'"
                f' {nginx_av}')
            sudo(r"sed -i '/#LE-PLACEHOLDER#/a\        return 301 https://$server_name$request_uri;'"
                f' {nginx_av}')
            sudo(r"sed -i '/#LE-PLACEHOLDER#/a\    location / {'"
                f' {nginx_av}')
            sudo(r"sed -i '/#LE-PLACEHOLDER#/a\ '"
                f' {nginx_av}')
            sudo(r"sed -i '/client_max_body_size/i\}'"
                f' {nginx_av}')
            sudo(r"sed -i '/client_max_body_size/i\ '"
                f' {nginx_av}')
            sudo(r"sed -i '/client_max_body_size/i\server{'"
                f' {nginx_av}')
            sudo(f"sed -i '/client_max_body_size/i\    listen 443 ssl http2{default_server}'"
                f' {nginx_av}')
            sudo(f"sed -i '/client_max_body_size/i\    listen [::]:443 ssl http2{default_server}'"
                f' {nginx_av}')
            sudo(f"sed -i '/client_max_body_size/i\    server_name {site_name};'"
                f' {nginx_av}')
            sudo(f"sed -i '/client_max_body_size/i\    include snippets\/ssl-{site_name}.conf;'"
                f' {nginx_av}')
            sudo(f"sed -i '/client_max_body_size/i\    include snippets\/ssl-params.conf;'"
                f' {nginx_av}')
            sudo(r"sed -i '/client_max_body_size/i\ '"
                f' {nginx_av}')
    if setup_le == 'True':
        with settings(warn_only=True):
            le_check = run(f"grep 'location /.well-known' {nginx_av}").failed
        if le_check:
            sudo(r"sed -i '/#LE-PLACEHOLDER#/a\    }'"
                f' {nginx_av}')
            sudo(r"sed -i '/#LE-PLACEHOLDER#/a\        allow all;'"
                f' {nginx_av}')
            sudo(r"sed -i '/#LE-PLACEHOLDER#/a\        root /var/www/letsencrypt;\'"
                f' {nginx_av}')
            sudo(r"sed -i '/#LE-PLACEHOLDER#/a\    location /.well-known/acme-challenge {'"
                f' {nginx_av}')
            sudo(r"sed -i '/#LE-PLACEHOLDER#/a\ '"
                f' {nginx_av}')

    if int(client_max) != 10:
        sudo('sed -i '
            f"'s/client_max_body_size 10M;/client_max_body_size {client_max}M;/g'")

    if setup_media == 'True':
        with settings(warn_only=True):
            media_check = run(f"grep 'location /media' {nginx_av}")
            if media_check.failed:
                media_snippet = f"""
    location /media {{
        alias /home/{env.user}/sites/{site_name}/media;
    }}
"""
                sudo(f"sed -i '/client_max_body_size/i\{media_snippet}'"
                    f' {nginx_av}')
    if not exists(f'{nginx_en}'):
        sudo(f'ln -s {nginx_av} /etc/nginx/sites-enabled/')

def _nginx_check_and_restart():
    sudo('nginx -t && nginx -s reload')

def _letsencrypt_get_cert(site_name, user_email=None):
    nginx = f'/etc/nginx/sites-available/{site_name}.nginx.conf'
    letsencrypt = f'/etc/letsencrypt/configs/{site_name}.conf'
    if not exists('/opt/letsencrypt'):
        sudo('git clone https://github.com/certbot/certbot /opt/letsencrypt')
    else:
        sudo('cd /opt/letsencrypt && git pull origin master')
    sudo('mkdir -p /var/www/letsencrypt'
        ' && chgrp www-data /var/www/letsencrypt'
        ' && chmod -R 755 /var/www/letsencrypt')
    if user_email is not None:
        email_command = f' && sed -i s/USEREMAIL/{user_email}/g'
        email_command += f' /etc/letsencrypt/configs/{site_name}.conf'
    else:
        email_command = ''

    if not exists(f'{letsencrypt}'):
        sudo('mkdir -p /etc/letsencrypt/configs')
        put('letsencrypt-domain.template.conf', f'/home/{env.user}/{site_name}.conf')
        sudo(f'mv /home/{env.user}/{site_name}.conf {letsencrypt}')
        sudo(f'sed -i s/SITENAME/{site_name}/g'
            f' {letsencrypt}' + email_command)
    run(
        f'cd /opt/letsencrypt'
        ' && ./certbot-auto --non-interactive --config'
        f' /etc/letsencrypt/configs/{site_name}.conf certonly'
    )
    _letsencrypt_cron_renew(site_name=site_name)

def _letsencrypt_cron_renew(site_name):
    run(f'mkdir -p /home/{env.user}/.local/bin')
    put('renew-letsencrypt.sh', f'/home/{env.user}/.local/bin/renew-letsencrypt.sh')
    sudo(f'chmod +x /home/{env.user}/.local/bin/renew-letsencrypt.sh')
    run(f"sed -i 's/SITENAME/{site_name}/g' /home/{env.user}/.local/bin/renew-letsencrypt.sh")
    sudo('mkdir -p /var/log/letsencrypt')
    run(f'echo "0 0 1 JAN,MAR,MAY,JUL,SEP,NOV * /home/{env.user}/.local/bin/renew-letsencrypt.sh" | tee -a | crontab ')



# Need to automate:
#  - lock down ssh
#    = change port from 22 to 46434
#    = copy local ssh key to remote
#    = disable password auth
#    = disable root login through ssh
#  - secure firewall
#  - install fail2ban
#    = configure fail2ban to work with nginx



    