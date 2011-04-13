#!/usr/bin/env python

import base64
import datetime
import logging
import os
import time
import yaml

from django.utils import simplejson 
from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp import util

from gaesessions import get_current_session

GRAPH_URL = 'https://graph.facebook.com/'

class PageData(db.Model):
    page_id     = db.StringProperty(required=True)
    bg_url      = db.StringProperty() # if they specify a background url, otherwise show the default one
    
    # all the text attrs a user can edit, otherwise they're all default
    text_next   = db.StringProperty() # the title, defaults to 'Next gig:'
    text_more   = db.StringProperty() # the sub title, defaults to 'More gigs:'
    text_time   = db.StringProperty() # prefix for date and time, defaults to 'Date &amp; time:'
    text_addr   = db.StringProperty() # prefix for address/location, defaults to 'Location:'
    css         = db.StringProperty() # should the user decide they want custom css, defaults to nothing

class EditHandler(webapp.RequestHandler):
    def post(self):
    #def get(self):
        # get the config
        c = Config().config
        
        # check for method
        if self.request.get( 'method' ):
            # now switch through the methods
            m = self.request.get( 'method' )
            
            # check user auth
            if m == 'auth':
                r = CheckUserPageAuth( self.request.get( 'access_token' ), self.request.get( 'fb_page_id' ) ).check
            
            # get the page data
            elif m == 'get_data':
                r = GetPageData().data
            
            # add/set page data
            elif m == 'add_data':
                r = AddPageData( self.request.body ).status
            
            # render return as json
            r = simplejson.dumps( r )
            
            # set the header as json
            self.response.headers[ 'Content-Type' ] = 'application/json'
            
            # and write it
            self.response.out.write( r )
            
        else:
            # get the request data
            r = ParseSignedRequest( self.request.get( 'signed_request' ) ).data
            
            # dump it as json
            r = simplejson.dumps( r )
            
            # prepare the template
            t = template.render(
                                    os.path.join( 
                                                    os.path.dirname( __file__ ), 
                                                    'template/edit.html' 
                                                ), 
                                    { 'd': c, 'r': r } 
                                )
            
            # and render it
            self.response.out.write( t )
    

class MainHandler(webapp.RequestHandler):
    def get(self):
        # get the config
        c = Config().config
        
        # nothing happens in get, so send them packing to Facebook
        self.redirect( 'http://www.facebook.com/apps/application.php?id=%d' % c[ 'fb' ][ 'app_id' ] );
    
    def post(self):
        # get the config
        c = Config().config
        
        # get the request data
        r = ParseSignedRequest( self.request.get( 'signed_request' ) ).data
        
        # get fb access key
        a = GetAccessKey( c[ 'fb' ][ 'app_id' ], c[ 'fb' ][ 'app_secret' ] ).token
        
        # now we want to get the page's events
        e = GetPageEvents( a, r[ 'page' ][ 'id' ] ).events
        
        # let's check to see if we have our user prefs cached
        d = memcache.get( 'prefs-' + r[ 'page' ][ 'id' ] )
        
        if d is None:
            # get current page data
            l = GetPageData( r[ 'page' ][ 'id' ] ).data
            
            # get default page data
            d = c[ 'data' ]
            
            # check if there is page data
            if l is not None:
                # we merge the bad boys
                d.update( l )
                
            # and stick it in the memcache
            memcache.add( 'prefs-' + r[ 'page' ][ 'id' ], d )
            
        
        # and now we prepare our template
        t = template.render(
                                os.path.join( 
                                                os.path.dirname( __file__ ), 
                                                'template/index.html' 
                                            ), 
                                { 'd': d, 'es': e[ 'es' ], 'ne': e[ 'ne' ] } )
        
        # and we write it :)
        self.response.out.write( t )
    

class Config(object):
    def __init__(self):
        # check for config in memcache
        c = memcache.get( 'config' )
        
        if c is None:
            # read the config
            f = open( 
                        os.path.join( 
                                        os.path.dirname( __file__ ),
                                        'config.yaml'
                                    ), 
                        'r'
                    )
            
            # yamlize its ass
            c = yaml.load( f.read() )
            
            # store in memcache
            memcache.add( 'config', c )
        
        # return it as a var
        self.config = c

class ParseSignedRequest(object):
    def __init__(self, req):
        # we split the request str into the encoded str and the payload
        r = req.split( '.' )
        
        self.request = r[ 1 ]
        self.payload = r[ 0 ]
        
        # now we'll get the data
        self.data = self._get_request_data()
        
    def _get_request_data(self):
        # base64 decode the string
        h = base64.decodestring( self.request + '==' )
        
        # now json decode its ass
        return simplejson.loads( h )

class GetAccessKey(object):
    def __init__(self, app_id, app_secret):
        self.id = app_id
        self.secret = app_secret
        
        # check for access token in memcache
        t = memcache.get( 'access_token' )
        
        if t is None:
            # now let's make the request and get the token
            t = self._get_access_token()
            
            # store access token to memcache
            memcache.add( 'access_token', t )
        
        # return the token
        self.token = t
        
    def _get_access_token(self):
        # format the url
        u = GRAPH_URL + 'oauth/access_token?client_id=%(id)s&client_secret=%(secret)s&grant_type=client_credentials' \
        % { 'id': self.id, 'secret': self.secret }
        
        # make the request
        r = urlfetch.fetch( u )
        
        if r.status_code == 200:
            # we just want the token thanks
            d = r.content.replace( 'access_token=', '' )
            
        return d

class GetPageEvents(object):
    def __init__(self, access_token, page_id):
        self.access_token = access_token
        self.page_id = page_id
        
        # check for events in memcache
        e = memcache.get( 'events-' + page_id )
        
        if e is None:
            # now make the request and return decoded json
            e = self._get_events()
            
            # store events to memcache
            memcache.add( 'events-' + page_id, e )
        
        # return the events
        self.events = e
        
    def _get_events(self):
        # prepare the url
        u = GRAPH_URL + self.page_id + '/events?access_token=%s' % self.access_token
        
        # make the request
        r = urlfetch.fetch( u )
        
        if r.status_code == 200:
            # decode the json
            d = simplejson.loads( r.content )[ 'data' ]
            
            # create an list for our future events
            e = [ ]
            
            # interate through the events to find the future ones
            for ev in d:
                t = datetime.datetime.strptime( ev[ 'start_time' ], '%Y-%m-%dT%H:%M:%S' ).timetuple() # convert fb time string from 2011-04-24T06:00:00+0000 to time
                
                c = time.mktime( t )
                
                # check to see if this event is in the future
                if c > time.time():
                    ev[ 'start_time' ] = time.strftime( '%a %d %b at %I:%M%p', t )
                    
                    e.append( ev )
                
            # reverse the list
            e.reverse()
            
            # construct final data object contain the next event and the upcoming events
            es = { 'ne': e.pop( 0 ), 'es': e }
            
        return es

class CheckUserPageAuth(object):
    def __init__(self, access_token, page_id):
        self.access_token = access_token
        self.page_id = page_id
        
        # run the check
        self.check = self._check_auth()
        
    def _check_auth(self):
        # prepare el url
        u = GRAPH_URL + '/me/accounts?access_token=%s' % self.access_token
        
        # make the request
        r = urlfetch.fetch( u )
        
        # we set the check as false
        c = False
        
        if r.status_code == 200:
            # decode the json
            d = simplejson.loads( r.content )[ 'data' ]
            
            # loop through their auth'd pages to see if they can access this one
            for a in d:
                # yay we found it
                if a[ 'id' ] == self.page_id:
                    c = True
                    
                    break
                
            
            # and now if we found the page, we set them a cookie
            if c:
                s = get_current_session()
                
                # set page_id session item
                s[ 'page_id' ] = self.page_id
            
        
        # return check
        return c
    

class GetPageData(object):
    def __init__(self, page_id=None):
        # check if page id has been supplied
        if page_id is None:
            # get the session
            s = get_current_session()
            
            # check for the page id
            if s.has_key( 'page_id' ):
                page_id = s[ 'page_id' ]
            
        
        # check for a valid page id
        if page_id is not None:
            # now get any info we have about this page from the ds
            q = db.GqlQuery( 'SELECT * FROM PageData WHERE page_id = :1', page_id ).get()
            
            if q is None:
                # it's their first time, return an empty list
                r = [ ]
            
            else:
                # now we need to update d with q's values
                ps = PageData.properties().iteritems()
                r = { }
                
                # we cycle through the properties of the model
                for k, p in ps:
                    v = getattr( q, k )
                    
                    # if the value isn't empty, we add it to the list
                    if v is not None and v != '':
                        r[ k ] = v
                    
                
            
            # return the data
            self.data = r
            
        else:
            # no session, no lighty
            self.data = False
        
    

class AddPageData(object):
    def __init__(self, body):
        # get the session
        self.session = get_current_session()
        
        # check for the page id
        if self.session.has_key( 'page_id' ):
            # since we get the request body, let's create a dict of it
            self.body = self._format_body( body )
            
            # now we parse the data
            self.status = self._parse_body()
        
        else:
            # oh dear
            self.status = False
        
    
    def _format_body(self, body):
        # get our dict ready
        b = { }
        
        # split the request into name=value
        r = body.split( '&' )
        
        # loop through them
        for i in r:
            # split each item into name, value
            i = i.split( '=' )
            
            # stick item into our dict
            b[ i[ 0 ] ] = i[ 1 ]
        
        # return the dict
        return b
    
    def _parse_body(self):
        # check to see if the page already has props in the ds
        q = db.GqlQuery( 'SELECT * FROM PageData WHERE page_id = :1', self.session[ 'page_id' ] ).get()
        
        # if there isn't one, create a new model instance
        if q is None:
            q = PageData( page_id=self.session[ 'page_id' ] )
        
        # set the properties for the model instance
        q.bg_url = self.body[ 'bg_url' ]
        q.text_next = self.body[ 'text_next' ]
        q.text_more = self.body[ 'text_more' ]
        q.text_time = self.body[ 'text_time' ]
        q.text_addr = self.body[ 'text_addr' ]
        q.css = self.body[ 'css' ]
        
        # now we put the model instance into the ds
        q.put()
        
        # and make sure we clear the memcache store
        memcache.delete( 'prefs-' + self.session[ 'page_id' ] )
        
        # and return true
        return True
    

def main():
    application = webapp.WSGIApplication( [
                                            ( '/', MainHandler ),
                                            ( '/edit/', EditHandler )
                                        ], debug=True )
    util.run_wsgi_app(application)

if __name__ == '__main__':
    main()
