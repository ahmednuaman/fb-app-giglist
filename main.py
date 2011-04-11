#!/usr/bin/env python

import base64
import datetime
import hmac
import json
import logging
import os
import time
import yaml

from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp import util

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
        self.response.out.write('Well..')

class MainHandler(webapp.RequestHandler):
    #def get(self):
        # nothing happens in get, so send them packing to Facebook
    #    self.redirect( 'http://www.facebook.com/apps/application.php?id=124030941005528' );
    
    #def post(self):
    def get(self):
        # get the config
        c = Config().config
        
        # get the request data
        r = ParseSignedRequest( self.request.get( 'signed_request' ) ).data
        
        # get fb access key
        a = GetAccessKey( c[ 'fb' ][ 'app_id' ], c[ 'fb' ][ 'app_secret' ] ).token
        
        # now we want to get the page's events
        e = GetPageEvents( a, r[ 'page' ][ 'id' ] ).events
        
        # now let's prepare the page defined vars
        q = db.GqlQuery( 'SELECT * FROM PageData WHERE page_id = :1', r[ 'page' ][ 'id' ] ).get()
        
        # get the default info
        d = c[ 'data' ]
        
        if q is not None:
            # now we need to update d with q's values
            ps = PageData.properties().iteritems()
            l = { }
            
            # we cycle through the properties of the model
            for k, p in ps:
                v = getattr( q, k )
                
                # if the value isn't empty, we add it to l
                if v is not None:
                    l[ k ] = v
                
            # finally, we merge the bad boys
            d.update( l )
            
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
            f = open( 'config.yaml', 'r' )
            
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
        return json.loads( h )

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
        
        # now make the request and return decoded json
        self.events = self._get_events()
        
    def _get_events(self):
        u = GRAPH_URL + self.page_id + '/events?access_token=%s' % self.access_token
        
        # make the request
        r = urlfetch.fetch( u )
        
        if r.status_code == 200:
            # decode the json
            d = json.loads( r.content )[ 'data' ]
            
            # create an list for our future events
            e = [ ]
            
            # interate through the events to find the future ones
            for ev in d:
                t = datetime.datetime.strptime( ev[ 'start_time' ], '%Y-%m-%dT%H:%M:%S' ) # convert fb time string from 2011-04-24T06:00:00+0000 to time
                
                # check to see if this event is in the future
                if time.mktime( t.timetuple() ) > time.time():
                   e.append( ev )
                
            # reverse the list
            e.reverse()
            
            # construct final data object contain the next event and the upcoming events
            es = { 'ne': e.pop( 0 ), 'es': e }
            
        return es

def main():
    application = webapp.WSGIApplication( [
                                            ( '/', MainHandler ),
                                            ( '/edit', EditHandler )
                                        ], debug=True )
    util.run_wsgi_app(application)

if __name__ == '__main__':
    main()
