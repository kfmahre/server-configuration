from flask import Flask, render_template, request, redirect, jsonify, url_for, flash
from sqlalchemy import create_engine, asc, desc, Table, MetaData
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Location, MenuItem, User
from flask import session as login_session
import random
import string
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests

APP_PATH = '/var/www/Catalog/Catalog/'
app = Flask(__name__, instance_relative_config=True)

CLIENT_ID = json.loads(
    open(APP_PATH + 'client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Running Store App"

engine = create_engine('postgresql://student:Lannister1@localhost/catalog')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()


# Create anti-forgery state token
@app.route('/login')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    return render_template('login.html', STATE=state)


@app.route('/fbconnect', methods=['POST'])
def fbconnect():
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    access_token = request.data
    print "access token received %s " % access_token

    app_id = json.loads(open(APP_PATH + 'fb_client_secrets.json', 'r').read())[
        'web']['app_id']
    app_secret = json.loads(
        open(APP_PATH + 'fb_client_secrets.json', 'r').read())['web']['app_secret']
    url = 'https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=%s&client_secret=%s&fb_exchange_token=%s' % (app_id,app_secret,access_token)
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]

    userinfo_url = 'https://graph.facebook.com/v2.4/me'
    token = result.split("&")[0]

    url = 'https://graph.facebook.com/v2.4/me?%s&fields=name,id,email' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    data = json.loads(result)
    login_session['provider'] = 'facebook'
    login_session['username'] = data["name"]
    login_session['email'] = data["email"]
    login_session['facebook_id'] = data["id"]

    # The token must be stored in the login_session in order to properly logout, let's strip out the information before the equals sign in our token
    stored_token = token.split("=")[1]
    login_session['access_token'] = stored_token

    url = 'https://graph.facebook.com/v2.4/me/picture?%s&redirect=0&height=200&width=200' % token
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    data = json.loads(result)

    login_session['picture'] = data["data"]["url"]

    user_id = getUserID(login_session["email"])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
    flash("you are now logged in as %s" % login_session['username'])
    print "done!"
    return output


@app.route('/fbdisconnect')
def fbdisconnect():
    facebook_id = login_session['facebook_id']
    # The access token must me included to successfully logout
    access_token = login_session['access_token']
    url = 'https://graph.facebook.com/%s/permissions?access_token=%s' % (facebook_id,access_token)
    h = httplib2.Http()
    result = h.request(url, 'DELETE')[1]
    return "you have been logged out"


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    request.get_data()
    code = request.data.decode('utf-8')

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets(APP_PATH + 'client_secrets.json', scope='')
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
        print "Token's client ID does not match app's."
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_credentials = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_credentials is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps(
                                 'Current user is already connected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['credentials'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['provider'] = 'google'
    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    # see if user exists, if it doesn't make a new one
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius: 150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;"> '
    flash("you are now logged in as %s" % login_session['username'])
    print "done!"
    return output


def createUser(login_session):
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None


@app.route('/gdisconnect')
def gdisconnect():
    # Only disconnect a connected user.
    credentials = login_session.get('credentials')
    if credentials is None:
        response = make_response(
            json.dumps('Current user not connected.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    access_token = login_session.get('credentials')
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    if result['status'] != '200':
        # For whatever reason, the given token was invalid.
        response = make_response(
            json.dumps('Failed to revoke token for given user.'), 400)
        response.headers['Content-Type'] = 'application/json'
        return response


# Disconnect based on provider
@app.route('/disconnect')
def disconnect():
    if 'provider' in login_session:
        if login_session['provider'] == 'google':
            gdisconnect()
            del login_session['gplus_id']
            del login_session['credentials']
        if login_session['provider'] == 'facebook':
            fbdisconnect()
            del login_session['facebook_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        del login_session['user_id']
        del login_session['provider']
        flash("You have successfully been logged out.")
        return redirect(url_for('showLocations'))
    else:
        flash("You were not logged in")
        return redirect(url_for('showLocations'))


@app.route('/locations/JSON')
def locationsJSON():
    location = session.query(Location).filter_by(id=Location.id)
    locations = session.query(Location).filter_by(
        name=Location.name).all()
    return jsonify(Locations=[location.serialize for location in
                   locations])


@app.route('/locations/byname/JSON')
@app.route('/locations/byname/asc/JSON')
def locationsByNameAscJSON():
    location = session.query(Location).filter_by(name=Location.name)
    locations = session.query(Location).filter_by(
        id=Location.id).order_by(asc(Location.name)).all()
    return jsonify(Locations=[
        location.serialize for location in locations])


@app.route('/locations/byname/desc/JSON')
def locationsByNameDescJSON():
    location = session.query(Location).filter_by(name=Location.name)
    locations = session.query(Location).filter_by(
        id=Location.id).order_by(desc(Location.name)).all()
    return jsonify(Locations=[
        location.serialize for location in locations])


@app.route('/location/<int:location_id>/menu/JSON')
def locationMenuJSON(location_id):
    location = session.query(Location).filter_by(id=location_id).one()
    items = session.query(MenuItem).filter_by(
        location_id=location_id).all()
    return jsonify(MenuItems=[i.serialize for i in items])


@app.route('/location/<int:location_id>/menu/<int:menu_id>/JSON')
def itemJSON(location_id, menu_id):
    item = session.query(MenuItem).filter_by(id=location_id).one()
    return jsonify(MenuItems=item.serialize)


@app.route('/')
@app.route('/location/')
def showLocations():
    locations = session.query(Location).all()
    if 'username' not in login_session:
        return render_template('publiclocations.html', items=locations)
    else:
        return render_template('locations.html', items=locations)


@app.route('/location/new/', methods=['GET', 'POST'])
def newLocation():
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        newLoc = Location(name=request.form['name'],
                             user_id=login_session['user_id'])
        session.add(newLoc)
        session.commit()
        flash("New Location created")
        return redirect(url_for('showLocations'))
    else:
        return render_template('newLocation.html')


@app.route('/location/<int:location_id>/edit', methods=['GET', 'POST'])
def editLocation(location_id):
    editedLocation = session.query(
        Location).filter_by(id=location_id).one()
    if 'username' not in login_session:
        return redirect('/login')
    if editedLocation.user_id != login_session['user_id']:
        return "<script>function myFunction() {alert('You are not authorized to edit this location. Please create your own location in order to edit.');}</script><body onload='myFunction()''>"
    if request.method == 'POST':
        if request.form['name']:
            editedLocation.name = request.form['name']
        session.add(editedLocation)
        session.commit()
        flash("Location updated")
        return redirect(url_for('showLocations'))
    else:
        return render_template('editLocation.html',
                               location_id=location_id,
                               location=editedLocation)


@app.route('/location/<int:location_id>/delete', methods=['GET', 'POST'])
def deleteLocation(location_id):
    deletedLocation = session.query(
        Location).filter_by(id=location_id).one()
    if 'username' not in login_session:
        return redirect('/login')
    if deletedLocation.user_id != login_session['user_id']:
        return "<script>function myFunction() {alert('You are not authorized to delete this location. Please create your own location in order to delete.');}</script><body onload='myFunction()''>"
    if request.method == 'POST':
        session.delete(deletedLocation)
        session.commit()
        flash("Location deleted")
        return redirect(url_for('showLocations'))
    else:
        return render_template('deleteLocation.html',
                               location_id=location_id,
                               location=deletedLocation)


@app.route('/location/<int:location_id>/')
@app.route('/location/<int:location_id>/menu/')
def showMenu(location_id):
    location = session.query(Location).filter_by(id=location_id).one()
    creator = getUserInfo(location.user_id)
    items = session.query(MenuItem).filter_by(
        location_id=location_id).all()
    if 'username' not in login_session or creator.id != login_session[
                                                        'user_id']:
        return render_template('publicmenu.html', location=location,
                               items=items, creator=creator)
    else:
        return render_template('menu.html', location=location,
                               items=items, creator=creator)


@app.route('/location/<int:location_id>/menu/new', methods=['GET', 'POST'])
def newMenuItem(location_id):
    if 'username' not in login_session:
        return redirect('/login')
    location = session.query(Location).filter_by(id=location_id).one()
    if login_session['user_id'] != location.user_id:
        return "<script>function myFunction() {alert('You are not authorized to add menu items to this location. Please create your own location in order to add items.');}</script><body onload='myFunction()''>"
    if request.method == 'POST':
        newItem = MenuItem(name=request.form['name'],
                           description=request.form['description'],
                           price=request.form['price'],
                           shoe_class=request.form['class'],
                           user_id=location.user_id,
                           location_id=location_id)
        session.add(newItem)
        session.commit()
        flash("New menu item created")
        return redirect(url_for('showMenu', location_id=location_id))
    else:
        return render_template('newmenuitem.html', location_id=location_id)


@app.route('/location/<int:location_id>/menu/<int:menu_id>/edit/',
           methods=['GET', 'POST'])
def editMenuItem(location_id, menu_id):
    if 'username' not in login_session:
        return redirect('/login')
    editedItem = session.query(MenuItem).filter_by(id=menu_id).one()
    location = session.query(Location).filter_by(id=location_id).one()
    if login_session['user_id'] != location.user_id:
        return "<script>function myFunction() {alert('You are not authorized to edit menu items to this location. Please create your own location in order to edit items.');}</script><body onload='myFunction()''>"
    if request.method == 'POST':
        if request.form['name']:
            editedItem.name = request.form['name']
        if request.form['description']:
            editedItem.description = request.form['description']
        if request.form['price']:
            editedItem.price = request.form['price']
        if request.form['class']:
            editedItem.shoe_class = request.form['class']
        session.add(editedItem)
        session.commit()
        flash("Item updated")
        return redirect(url_for('showMenu', location_id=location_id))
    else:
        # USE THE RENDER_TEMPLATE FUNCTION BELOW TO SEE THE VARIABLES YOU SHOULD USE IN YOUR EDITMENUITEM TEMPLATE
        return render_template('editmenuitem.html',
                               location_id=location_id,
                               menu_id=menu_id,
                               item=editedItem)


@app.route('/location/<int:location_id>/menu/<int:menu_id>/delete/',
           methods=['GET', 'POST'])
def deleteMenuItem(location_id, menu_id):
    if 'username' not in login_session:
        return redirect('/login')
    location = session.query(Location).filter_by(id=location_id).one()
    deletedItem = session.query(MenuItem).filter_by(id=menu_id).one()
    if login_session['user_id'] != location.user_id:
        return "<script>function myFunction() {alert('You are not authorized to delete menu items to this location. Please create your own location in order to delete items.');}</script><body onload='myFunction()''>"
    if request.method == 'POST':
        session.delete(deletedItem)
        session.commit()
        flash("Item deleted")
        return redirect(url_for('showMenu', location_id=location_id))
    else:
        return render_template('deletemenuitem.html',
                               location_id=location_id,
                               item=deletedItem)


@app.route('/clearSession')
def clearSession():
    login_session.clear()
    return "Session cleared"


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = True
    app.run(host='127.0.0.1', port=8080)
