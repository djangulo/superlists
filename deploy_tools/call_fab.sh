#!/bin/sh

PORT=43464

STAGING_SITE=superlists.djangulo.com
PROJECT_NAME='superlists'
DEFAULT=False
MEDIA=False
SSL=True
STATIC=False
CLIENT_MAX=10

fab --set project_name=$PROJECT_NAME,default=$DEFAULT,media=$MEDIA,\
ssl=$SSL,static=$STATIC,c_max=$CLIENT_MAX \
deploy:host=$USER@$STAGING_SITE --port $PORT

# project_name = env['project_name']
# default = env.get('default', False)
# media = env.get('media', False)
# ssl = env.get('ssl', False)
# static = env.get('static', False)
# c_max = env.get('client_max', 10)

