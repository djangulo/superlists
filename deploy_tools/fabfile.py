from fabric.contrib.files import append, exists, sed
from fabric.api import env, local, run, sudo, put
import random

REPO_URL = 'https://github.com/djangulo/superlists.git'

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

def _prepare_basic_nginx_file():
    pass

def _configure_nginx(site_name, setup_media=False, setup_static=False,
    ssl_redirect=False):
    if ssl_redirect:
        if exists(f'/etc/nginx/sites-available/{site_name}.nginx.conf'):
            sudo(
                'mv /home/{env.user}/ssl-params.conf /etc/nginx/snippets/ssl-params.conf'
                """&& sed '/server_name/a\"
                    return 301 https://$server_name$request_uri;\n'"""
                ' /etc/nginx/sites-available/{site_name}.nginx.conf'
            )
        else:
            put('nginx.template.conf', '/home/{env.user}/{site_name}.nginx.conf')
            sudo(
                f'mv /home/{env.user}/nginx.template.conf'
                ' /etc/nginx/sites-available/{site_name}.nginx.conf'
                ' && sed s/SITENAME/{site_name}/g'
                ' /etc/nginx/sites-available/{site_name}.nginx.conf'
                ' | tee /etc/nginx/sites-available/{site_name}.nginx.conf'
                ' && sed s/USERNAME/{env.user}/g'
                ' /etc/nginx/sites-available/{site_name}.nginx.conf'
                ' | tee /etc/nginx/sites-available/{site_name}.nginx.conf'
                " && sed 's:#--LETSENCRYPT_PLACEHOLDER--#:"
                "    location /.well-known/acme-challenge {\n"
                "        root /var/www/letsencrypt;\n"
                "    }:g' /etc/nginx/sites-available/{site_name}.nginx.conf"
                ' | tee /etc/nginx/sites-available/{site_name}.nginx.conf'
                ' && ln -s /etc/nginx/sites-available/{site_name}.nginx.conf'
                ' /etc/nginx/sites-enabled/'
                ' && nginx -t && nginx -s reload'
            )

def _letsencrypt_get_cert(site_name, user_email=None, *args, **kwargs):
    if not exists('/opt/letsencrypt'):
        sudo('git clone https://github.com/certbot/certbot /opt/letsencrypt')
    else:
        sudo(
            'cd /opt/letsencrypt'
            ' && git pull origin master'
        )
    sudo(
        ' mkdir -p /var/www/letsencrypt'
        ' && chgrp www-data /var/www/letsencrypt'
        )
    if user_email is not None:
        email_command = f' && sed s/USEREMAIL/{user_email}/g'
        email_command += f' /etc/letsencrypt/configs/{site_name}.conf'
        email_command += f' | tee /etc/letsencrypt/configs/{site_name}.conf'
    else:
        email_command = ''

    if exists(f'/etc/letsencrypt/configs/{site_name}.conf') == False:
        sudo('mkdir -p /etc/letsencrypt/configs')
        put('letsencrypt-domain.template.conf', f'/home/{env.user}/{site_name}.conf')
        sudo(
            f'mv /home/{env.user}/{site_name}.conf'
            ' /etc/letsencrypt/configs/{site_name}.conf'
            ' && sed s/SITENAME/{site_name}/g'
            ' /etc/letsencrypt/configs/{site_name}.conf'
            ' | tee /etc/letsencrypt/configs/{site_name}.conf' + email_command
        )
    if exists(f'/etc/nginx/sites-available/{site_name}.nginx.conf'):
        sudo(
            f'sed s/#--LETSENCRYPT_PLACEHOLDER--#/'
            '    location /.well-known/acme-challenge {\n'
            '        root /var/www/letsencrypt;\n'
            '    }/g'
            f' /etc/nginx/sites-available/{site_name}.nginx.conf'
            f' | tee /etc/nginx/sites-available/{site_name}.nginx.conf'
            ' && nginx -t && nginx -s reload'
        )
    else:
        put('nginx.template.conf', f'/home/{env.user}/{site_name}.nginx.conf')
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



    