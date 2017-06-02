from fabric.contrib.files import append, exists, sed
from fabric.api import env, local, run, sudo, put
import random

REPO_URL = 'https://github.com/djangulo/superlists.git'

env['sudo_user'] = 'djangulo'

def deploy():
    site_folder = f'/home/{env.user}/sites/{env.host}'
    source_folder = site_folder + '/source'
    _install_necessary_packages()
    _create_directory_structure_if_necessary(site_folder)
    _get_latest_source(source_folder)
    _update_settings(source_folder, env.host)
    _update_virtualenv(source_folder)
    _update_static_files(source_folder)
    _update_database(source_folder)

def get_ssl_cert():
    _letsencrypt_get_cert(env.host, 'denis.angulo@linekode.com')

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

def _update_settings(source_folder, site_name):
    settings_path = source_folder + '/superlists/settings.py'
    sed(settings_path, "DEBUG = True", "DEBUG = False")
    sed(
        settings_path,
        'ALLOWED_HOSTS = .+$',
        f'ALLOWED_HOSTS = ["{site_name}"]'
    )
    secret_key_file = source_folder + '/superlists/secret_key.py'
    if not exists(secret_key_file):
        chars = 'abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)'
        key = ''.join(random.SystemRandom().choice(chars) for _ in range(50))
        append(secret_key_file, f'SECRET_KEY = "{key}"')
    append(settings_path, '\nfrom .secret_key import SECRET_KEY')

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
    setup_static=False, ssl_redirect=False, client_max=10):
    default_server = ' default_server;' if is_default_server else ';'
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
        
    if is_default_server:
        sudo(f"sed -i 's/listen 80;/listen 80{default_server}/g'"
            f' {nginx_av}')
        sudo(f"sed -i 's/listen [::]:80;/listen [::]:80{default_server}/g'"
            f' {nginx_av}')
    if ssl_redirect:
        ssl_snippet = f"""server{{
    listen 443 ssl http2{default_server}
    listen [::]:443 ssl http2{default_server}
    include snippets/ssl-{site_name}.conf;
    include snippets/ssl-params.conf;

"""
        put('ssl-params.conf', f'/home/{env.user}/ssl-params.conf')
        sudo(f'mv /home/{env.user}/ssl-params.conf'
            ' /etc/nginx/snippets/ssl-params.conf')
        sudo("sed -i"
            " '/charset utf-8/i\    return 301 https://$server_name$request_uri;\n'"
            f' {nginx_av}')
        sudo("sed -i '/charset utf-8/a\}'"
            f' {nginx_av}')
        sudo(f"sed -i '/client_max_body_size/i\{ssl_snippet}"
            f' {nginx_av}')
    if client_max != 10:
        sudo('sed -i '
            f"'s/client_max_body_size 10M;/client_max_body_size {client_max}M;/g'")
    if setup_media:
        media_snippet = f"""
    location /media {{
        alias /home/{env.user}/sites/{site_name}/media;
    }}
"""
        sudo(f"sed -i '/client_max_body_size/i\{media_snippet}'"
            f' {nginx_av}')
    if not exists(f'{nginx_en}'):
        sudo(f'ln -s {nginx_av} /etc/nginx/sites-enabled/')
    sudo('nginx -t && nginx -s reload')

def _letsencrypt_get_cert(site_name, user_email=None, *args, **kwargs):
    nginx = f'/etc/nginx/sites-available/{site_name}.nginx.conf'
    letsencrypt = f'/etc/letsencrypt/configs/{site_name}.conf'
    if not exists('/opt/letsencrypt'):
        sudo('git clone https://github.com/certbot/certbot /opt/letsencrypt')
    else:
        sudo('cd /opt/letsencrypt && git pull origin master')
    sudo('mkdir -p /var/www/letsencrypt'
        ' && chgrp www-data /var/www/letsencrypt')
    if user_email is not None:
        email_command = f' && sed -i s/USEREMAIL/{user_email}/g'
        email_command += f' /etc/letsencrypt/configs/{site_name}.conf'
    else:
        email_command = ''

    if not exists(f'{letsencrypt}'):
        sudo('mkdir -p /etc/letsencrypt/configs')
        put('letsencrypt-domain.template.conf', f'/home/{env.user}/{site_name}.conf')
        sudo(f'mv /home/{env.user}/{site_name}.conf {letsencrypt}')
        sudo('sed -i s/SITENAME/{site_name}/g'
            ' {letsencrypt}' + email_command)
    if exists(f'{nginx}'):
        sudo(
            f'sed -i s/#--LETSENCRYPT_PLACEHOLDER--#/'
            '    location /.well-known/acme-challenge {\n'
            '        root /var/www/letsencrypt;\n'
            '    }/g'
            f' {nginx}'
            ' && nginx -t && nginx -s reload'
        )
    else:
        _configure_nginx(site_name=site_name)
        put('gunicorn-nginx.template.conf', f'/home/{env.user}/{site_name}.nginx.conf')
        sudo(
            f'mv /home/{env.user}/{site_name}.nginx.conf'
            f' /etc/nginx/sites-available/{site_name}.nginx.conf'
            f' && sed s/SITENAME/{site_name}/g'
            f' /etc/nginx/sites-available/{site_name}.nginx.conf'
            f' | tee /etc/nginx/sites-available/{site_name}.nginx.conf'
            f' && sed s/USERNAME/{env.user}/g'
            f' /etc/nginx/sites-available/{site_name}.nginx.conf'
            f' | tee /etc/nginx/sites-available/{site_name}.nginx.conf'
            " && sed 's:#--LETSENCRYPT_PLACEHOLDER--#:"
            "    location /.well-known/acme-challenge {\n"
            "        root /var/www/letsencrypt;\n"
            "    }:g'"
            f' /etc/nginx/sites-available/{site_name}.nginx.conf'
            f' | tee /etc/nginx/sites-available/{site_name}.nginx.conf'
            f' && ln -s /etc/nginx/sites-available/{site_name}.nginx.conf'
            ' /etc/nginx/sites-enabled/'
            ' && nginx -t && nginx -s reload'
        )
    run(
        f'cd /opt/letsencrypt'
        ' && ./certbot-auto --non-interactive --config'
        f' /etc/letsencrypt/configs/{site_name}.conf certonly'
    )

def _letsencrypt_configure_nginx(site_name):
    sudo(
        f'mkdir -p /etc/ssl/certs/'
        ' && openssl dhparam -out /etc/ssl/certs/dhparam.pem 2048'
        ' && echo "ssl_certificate /etc/letsencrypt/live/{site_name}/fullchain.pem;"'
        ' | tee /etc/nginx/snippets/ssl-{site_name}.conf'
        ' && echo "ssl_certificate_key /etc/letsencrypt/live/{site_name}/privkey.pem;"'
        ' | tee -a /etc/nginx/snippets/ssl-{site_name}.conf'
    )
    put('ssl-params.conf', '/home/{env.user}/ssl-params.conf')
    sudo(
        'mv /home/{env.user}/ssl-params.conf /etc/nginx/snippets/ssl-params.conf'
        """ && sed '/server_name/a \
            return 301 https://$server_name$request_uri;\n'"""
        ' /etc/nginx/sites-available/{site_name}.nginx.conf'
    )

# sed '/server_name/a \
#     return 301 https://$server_name$request_uri;' /etc/nginx/sites-available/merkablue.com.nginx.conf | sudo tee /etc/nginx/sites-available/merkablue.com.nginx.conf

# Need to automate:
#  - lock down ssh
#  - secure firewall
#  - install fail2ban
#    = configure fail2ban to work with nginx



    