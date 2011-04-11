#!/usr/bin/env python

import yaml

from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util

class App(db.Model):
    page_id     = db.StringProperty(required=True)
    bg_url      = db.StringProperty() # if they specify a background url, otherwise show the default one
    
    # all the text attrs a user can edit, otherwise they're all default
    text_next   = db.StringProperty() # the title, defaults to 'Next gig:'
    text_more   = db.StringProperty() # the sub title, defaults to 'More gigs:'
    text_time   = db.StringProperty() # prefix for date and time, defaults to 'Date &amp; time:'
    text_addr   = db.StringProperty() # prefix for address/location, defaults to 'Location:'
    text_des    = db.StringProperty() # prefix for description, defaults to 'Description:'

class MainHandler(webapp.RequestHandler):
    def get(self):
        # nothing happens in get, so send them packing to Facebook
        self.redirect( 'http://www.facebook.com/apps/application.php?id=124030941005528' );
    
    def post(self):
        self.response.out.write( 'Pow!' )

def main():
    application = webapp.WSGIApplication( [
                                            ( '/', MainHandler ) 
                                        ], debug=True )
    util.run_wsgi_app(application)

if __name__ == '__main__':
    main()
