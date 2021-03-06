#!/usr/bin/python3
import random
import string
import httplib2
import json
import requests

from flask import request
from flask import redirect, url_for, flash, make_response
from flask import session as login_session
from db_controller import DatabaseController

from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError

CLIENT_ID = json.loads(open('client_secrets.json', 'r')
                       .read())['web']['client_id']

db = DatabaseController()
token_info = ''


class Authentication:

    @staticmethod
    def google_connection():
        # Validate state token
        if request.args.get('state') != login_session['state']:
            response = make_response(
                json.dumps('Invalid state parameter.'), 401)
            response.headers['Content-Type'] = 'application/json'
            return response

        request.get_data()
        code = request.data.decode('utf-8')

        try:
            # Upgrade the authorization code into a credentials object
            oauth_flow = flow_from_clientsecrets('client_secrets.json',
                                                 scope='')
            oauth_flow.redirect_uri = 'postmessage'
            credentials = oauth_flow.step2_exchange(code)
        except FlowExchangeError:
            response = make_response(
                json.dumps('Failed to upgrade the authorization code.'), 401)
            response.headers['Content-Type'] = 'application/json'
            return response

        # Check that the access token is valid.
        access_token = credentials.access_token
        url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
               % access_token)
        # Submit request, parse response - Python3 compatible
        h = httplib2.Http()
        response = h.request(url, 'GET')[1]
        str_response = response.decode('utf-8')
        result = json.loads(str_response)
        # If there was an error in the access token info, abort.
        if result.get('error') is not None:
            response = make_response(json.dumps(result.get('error')), 500)
            response.headers['Content-Type'] = 'application/json'
            return response

        # Verify that the access token is used for the intended user.
        gplus_id = credentials.id_token['sub']

        if result['user_id'] != gplus_id:
            response = make_response(
                json.dumps("Token's user ID doesn't match given user ID."), 401)
            response.headers['Content-Type'] = 'application/json'
            return response

        # Verify that the access token is valid for this app.
        if result['issued_to'] != CLIENT_ID:
            response = make_response(
                json.dumps("Token's client ID does not match app's."), 401)
            response.headers['Content-Type'] = 'application/json'
            return response

        stored_access_token = login_session.get('access_token')
        stored_gplus_id = login_session.get('gplus_id')

        if stored_access_token is not None and gplus_id == stored_gplus_id:

            connuser = db.read_user(login_session)
            login_session['user_type_id'] = connuser['user_type_id']
            response = make_response(
                json.dumps('Current user is already connected.'), 200)
            response.headers['Content-Type'] = 'application/json'
            return response
        print('still going?')
        # Store the access token in the session for later use.
        login_session['access_token'] = access_token
        login_session['gplus_id'] = gplus_id

        # Get user info
        userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
        params = {'access_token': access_token, 'alt': 'json'}
        answer = requests.get(userinfo_url, params=params)

        data = answer.json()

        login_session['name'] = data['name']
        login_session['picture'] = data['picture']
        login_session['email'] = data['email']

        # see if user exists, if it doesn't make a new one
        user_id = db.read_user(login_session)
        print('')
        print(user_id)

        if not user_id.id:
            print(user_id)
            user_id = db.create_user(login_session)
        login_session['user_id'] = user_id.id
        login_session['user_type_id'] = user_id.user_type_id

        output = '<h1>redirecting...</h1>'
        flash("you are now logged in as %s" % login_session['name'], 'success')
        return output

    @staticmethod
    def logout():
        if login_session.get('access_token')is None:
            return json_response('Current user not connected', 401)
        url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' \
              % login_session.get('access_token')
        h = httplib2.Http()
        result = h.request(url, 'GET')[0]
        if result['status'] == '200':
            del login_session['access_token']
            del login_session['gplus_id']
            del login_session['name']
            del login_session['picture']
            del login_session['email']
            del login_session['user_id']
            return redirect(url_for('render_categories'))
        else:
            return json_response('Failed to revoke token for given user.', 400)

    @staticmethod
    def set_token_info(token):
        """Set the token into the global"""
        global token_info
        token_info = token

    @staticmethod
    def create_session():
        """Verify the session exists or make a new one"""
        if login_session.get('state') is None:
            login_session['state'] = ''.join(random.choice(
                string.ascii_uppercase + string.digits) for _ in range(32))
            return login_session


def json_response(message, response_code):
    """Build a JSON output"""
    response = make_response(json.dumps(message), response_code)
    response.headers['Content-Type'] = 'application/json'
    return response