import datetime
import json
import logging
import re
import time

from google.appengine.ext import db
# from google.appengine.ext.db import djangoforms
from google.appengine.api import mail
from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.api import taskqueue
from google.appengine.api import users

import settings
import util

#from django.forms import ModelForm
from collections import OrderedDict
from django import forms
# import google.appengine.ext.django as django


SIMPLE_TYPES = (int, long, float, bool, dict, basestring, list)

WEBCOMPONENTS = 1
MISC = 2
SECURITY = 3
MULTIMEDIA = 4
DOM = 5
FILE = 6
OFFLINE = 7
DEVICE = 8
COMMUNICATION = 9
JAVASCRIPT = 10
NETWORKING = 11
INPUT = 12
PERFORMANCE = 13
GRAPHICS = 14
CSS = 15

FEATURE_CATEGORIES = {
  CSS: 'CSS',
  WEBCOMPONENTS: 'Web Components',
  MISC: 'Misc',
  SECURITY: 'Security',
  MULTIMEDIA: 'Multimedia',
  DOM: 'DOM',
  FILE: 'File APIs',
  OFFLINE: 'Offline / Storage',
  DEVICE: 'Device',
  COMMUNICATION: 'Realtime / Communication',
  JAVASCRIPT: 'JavaScript',
  NETWORKING: 'Network / Connectivity',
  INPUT: 'User input',
  PERFORMANCE: 'Performance',
  GRAPHICS: 'Graphics',
  }

NO_ACTIVE_DEV = 1
PROPOSED = 2
IN_DEVELOPMENT = 3
BEHIND_A_FLAG = 4
ENABLED_BY_DEFAULT = 5
DEPRECATED = 6
REMOVED = 7
ORIGIN_TRIAL = 8
INTERVENTION = 9
NO_LONGER_PURSUING = 1000 # insure bottom of list

IMPLEMENTATION_STATUS = OrderedDict()
IMPLEMENTATION_STATUS[NO_ACTIVE_DEV] = 'No active development'
IMPLEMENTATION_STATUS[PROPOSED] = 'Proposed'
IMPLEMENTATION_STATUS[IN_DEVELOPMENT] = 'In development'
IMPLEMENTATION_STATUS[BEHIND_A_FLAG] = 'Behind a flag'
IMPLEMENTATION_STATUS[ORIGIN_TRIAL] = 'Origin trial'
IMPLEMENTATION_STATUS[INTERVENTION] = 'Browser Intervention'
IMPLEMENTATION_STATUS[ENABLED_BY_DEFAULT] = 'Enabled by default'
IMPLEMENTATION_STATUS[DEPRECATED] = 'Deprecated'
IMPLEMENTATION_STATUS[REMOVED] = 'Removed'
IMPLEMENTATION_STATUS[NO_LONGER_PURSUING] = 'No longer pursuing'

MAJOR_NEW_API = 1
MAJOR_MINOR_NEW_API = 2
SUBSTANTIVE_CHANGES = 3
MINOR_EXISTING_CHANGES = 4
EXTREMELY_SMALL_CHANGE = 5

FOOTPRINT_CHOICES = {
  MAJOR_NEW_API: ('A major new independent API (e.g. adding a large # '
                  'independent concepts with many methods/properties/objects)'),
  MAJOR_MINOR_NEW_API: ('Major changes to an existing API OR a minor new '
                        'independent API (e.g. adding a large # of new '
                        'methods/properties or introducing new concepts to '
                        'augment an existing API)'),
  SUBSTANTIVE_CHANGES: ('Substantive changes to an existing API (e.g. small '
                        'number of new methods/properties)'),
  MINOR_EXISTING_CHANGES: (
      'Minor changes to an existing API (e.g. adding a new keyword/allowed '
      'argument to a property/method)'),
  EXTREMELY_SMALL_CHANGE: ('Extremely small tweaks to an existing API (e.g. '
                           'how existing keywords/arguments are interpreted)'),
  }

MAINSTREAM_NEWS = 1
WARRANTS_ARTICLE = 2
IN_LARGER_ARTICLE = 3
SMALL_NUM_DEVS = 4
SUPER_SMALL = 5

VISIBILITY_CHOICES = {
  MAINSTREAM_NEWS: 'Likely in mainstream tech news',
  WARRANTS_ARTICLE: 'Will this feature generate articles on sites like html5rocks.com',
  IN_LARGER_ARTICLE: 'Covered as part of a larger article but not on its own',
  SMALL_NUM_DEVS: 'Only a very small number of web developers will care about',
  SUPER_SMALL: "So small it doesn't need to be covered in this dashboard.",
  }

SHIPPED = 1
IN_DEV = 2
PUBLIC_SUPPORT = 3
MIXED_SIGNALS = 4
NO_PUBLIC_SIGNALS = 5
PUBLIC_SKEPTICISM = 6
OPPOSED = 7

VENDOR_VIEWS = {
  SHIPPED: 'Shipped',
  IN_DEV: 'In development',
  PUBLIC_SUPPORT: 'Public support',
  MIXED_SIGNALS: 'Mixed public signals',
  NO_PUBLIC_SIGNALS: 'No public signals',
  PUBLIC_SKEPTICISM: 'Public skepticism',
  OPPOSED: 'Opposed',
  }

DEFACTO_STD = 1
ESTABLISHED_STD = 2
WORKING_DRAFT = 3
EDITORS_DRAFT = 4
PUBLIC_DISCUSSION = 5
NO_STD_OR_DISCUSSION = 6

STANDARDIZATION = {
  DEFACTO_STD: 'De-facto standard',
  ESTABLISHED_STD: 'Established standard',
  WORKING_DRAFT: 'Working draft or equivalent',
  EDITORS_DRAFT: "Editor's draft",
  PUBLIC_DISCUSSION: 'Public discussion',
  NO_STD_OR_DISCUSSION: 'No public standards discussion',
  }

DEV_STRONG_POSITIVE = 1
DEV_POSITIVE = 2
DEV_MIXED_SIGNALS = 3
DEV_NO_SIGNALS = 4
DEV_NEGATIVE = 5
DEV_STRONG_NEGATIVE = 6

WEB_DEV_VIEWS = {
  DEV_STRONG_POSITIVE: 'Strongly positive',
  DEV_POSITIVE: 'Positive',
  DEV_MIXED_SIGNALS: 'Mixed signals',
  DEV_NO_SIGNALS: 'No signals',
  DEV_NEGATIVE: 'Negative',
  DEV_STRONG_NEGATIVE: 'Strongly negative',
  }

def del_none(d):
  """
  Delete dict keys with None values, and empty lists, recursively.
  """
  for key, value in d.items():
    if value is None or (isinstance(value, list) and len(value) == 0):
      del d[key]
    elif isinstance(value, dict):
      del_none(value)
  return d

def list_to_chunks(l, n):
  """Yield successive n-sized chunk lists from l."""
  for i in xrange(0, len(l), n):
    yield l[i:i + n]


class DictModel(db.Model):
  # def to_dict(self):
  #   return dict([(p, unicode(getattr(self, p))) for p in self.properties()])

  def format_for_template(self):
    d = self.to_dict()
    d['id'] = self.key().id()
    return d

  def to_dict(self):
    output = {}

    for key, prop in self.properties().iteritems():
      value = getattr(self, key)

      if value is None or isinstance(value, SIMPLE_TYPES):
        output[key] = value
      elif isinstance(value, datetime.date):
        # Convert date/datetime to ms-since-epoch ("new Date()").
        #ms = time.mktime(value.utctimetuple())
        #ms += getattr(value, 'microseconds', 0) / 1000
        #output[key] = int(ms)
        output[key] = unicode(value)
      elif isinstance(value, db.GeoPt):
        output[key] = {'lat': value.lat, 'lon': value.lon}
      elif isinstance(value, db.Model):
        output[key] = to_dict(value)
      elif isinstance(value, users.User):
        output[key] = value.email()
      else:
        raise ValueError('cannot encode ' + repr(prop))

    return output


class BlinkComponent(DictModel):

  DEFAULT_COMPONENT = 'Blink'
  COMPONENTS_URL = 'https://blinkcomponents-b48b5.firebaseapp.com'
  COMPONENTS_ENDPOINT = '%s/blinkcomponents' % COMPONENTS_URL
  WF_CONTENT_ENDPOINT = '%s/wfcomponents' % COMPONENTS_URL

  name = db.StringProperty(required=True, default=DEFAULT_COMPONENT)
  created = db.DateTimeProperty(auto_now_add=True)
  updated = db.DateTimeProperty(auto_now=True)

  @property
  def owners(self):
    q = FeatureOwner.all().filter('blink_components = ', self.key()).order('name')
    return q.fetch(None)

  @classmethod
  def fetch_all_components(self, update_cache=False):
    """Returns the list of blink components from live endpoint if unavailable in the cache."""
    key = '%s|blinkcomponents' % (settings.MEMCACHE_KEY_PREFIX)

    components = memcache.get(key)
    if components is None or update_cache:
      components = []
      result = urlfetch.fetch(self.COMPONENTS_ENDPOINT, deadline=60)
      if result.status_code == 200:
        components = sorted(json.loads(result.content))
        memcache.set(key, components)
      else:
        logging.error('Fetching blink components returned: %s' % result.status_code)
    return components

  @classmethod
  def fetch_wf_content_for_components(self, update_cache=False):
    """Returns the /web content that use each blink component."""
    key = '%s|wfcomponents' % (settings.MEMCACHE_KEY_PREFIX)

    components = memcache.get(key)
    if components is None or update_cache:
      components = {}
      result = urlfetch.fetch(self.WF_CONTENT_ENDPOINT, deadline=60)
      if result.status_code == 200:
        components = json.loads(result.content)
        memcache.set(key, components)
      else:
        logging.error('Fetching /web blink components content returned: %s' % result.status_code)
    return components

  @classmethod
  def update_db(self):
    """Updates the db with new Blink components from the json endpoint"""
    self.fetch_wf_content_for_components(update_cache=True) # store /web content in memcache
    new_components = self.fetch_all_components(update_cache=True)
    existing_comps = self.all().fetch(None)
    for name in new_components:
      if not len([x.name for x in existing_comps if x.name == name]):
        logging.info('Adding new BlinkComponent: ' + name)
        c = BlinkComponent(name=name)
        c.put()

  @classmethod
  def get_by_name(self, component_name):
    """Fetch blink component with given name."""
    q = self.all()
    q.filter('name =', component_name)
    component = q.fetch(1)
    if not component:
      logging.error('%s is an unknown BlinkComponent.' % (component_name))
      return None
    return component[0]

# UMA metrics.
class StableInstance(DictModel):
  created = db.DateTimeProperty(auto_now_add=True)
  updated = db.DateTimeProperty(auto_now=True)

  property_name = db.StringProperty(required=True)
  bucket_id = db.IntegerProperty(required=True)
  date = db.DateProperty(verbose_name='When the data was fetched',
                         required=True)
  #hits = db.IntegerProperty(required=True)
  #total_pages = db.IntegerProperty()
  day_percentage = db.FloatProperty()
  rolling_percentage = db.FloatProperty()


class AnimatedProperty(StableInstance):
  pass


class FeatureObserver(StableInstance):
  pass


# Feature dashboard.
class Feature(DictModel):
  """Container for a feature."""

  DEFAULT_MEMCACHE_KEY = '%s|features' % (settings.MEMCACHE_KEY_PREFIX)
  MAX_CHUNK_SIZE = 500 # max num features to save for each memcache chunk.

  @classmethod
  def get_feature_chunk_memcache_keys(self, key_prefix):
    num_features = Feature.all(keys_only=True).count()
    l = list_to_chunks(range(0, num_features), self.MAX_CHUNK_SIZE)
    return ['%s|chunk%s' % (key_prefix, i) for i,val in enumerate(l)]

  @classmethod
  def set_feature_chunk_memcache_keys(self, key_prefix, feature_list):
    chunks = list_to_chunks(feature_list, self.MAX_CHUNK_SIZE)
    vals = []
    for i, chunk in enumerate(chunks):
      vals.append(('%s|chunk%s' % (key_prefix, i), chunk))
    # d = OrderedDict(sorted(dict(vals).items(), key=lambda t: t[0]))
    d = dict(vals)
    return d

  @classmethod
  def _first_of_milestone(self, feature_list, milestone, start=0):
    for i in xrange(start, len(feature_list)):
      f = feature_list[i]
      if (str(f['shipped_milestone']) == str(milestone) or
          f['impl_status_chrome'] == str(milestone)):
        return i
      elif (f['shipped_milestone'] == None and
            str(f['shipped_android_milestone']) == str(milestone)):
        return i

    return -1

  @classmethod
  def _first_of_milestone_v2(self, feature_list, milestone, start=0):
    for i in xrange(start, len(feature_list)):
      f = feature_list[i]
      desktop_milestone = f['browsers']['chrome'].get('desktop', None)
      android_milestone = f['browsers']['chrome'].get('android', None)
      status = f['browsers']['chrome']['status'].get('text', None)

      if (str(desktop_milestone) == str(milestone) or status == str(milestone)):
        return i
      elif (desktop_milestone == None and str(android_milestone) == str(milestone)):
        return i

    return -1

  @classmethod
  def _annotate_first_of_milestones(self, feature_list, version=None):
    try:
      omaha_data = util.get_omaha_data()

      win_versions = omaha_data[0]['versions']

      # Find the latest canary major version from the list of windows versions.
      canary_versions = [x for x in win_versions if x.get('channel') and x.get('channel').startswith('canary')]
      LATEST_VERSION = int(canary_versions[0].get('version').split('.')[0])

      milestones = range(1, LATEST_VERSION + 1)
      milestones.reverse()
      versions = [
        IMPLEMENTATION_STATUS[NO_ACTIVE_DEV],
        IMPLEMENTATION_STATUS[PROPOSED],
        IMPLEMENTATION_STATUS[IN_DEVELOPMENT],
        ]
      versions.extend(milestones)
      versions.append(IMPLEMENTATION_STATUS[NO_LONGER_PURSUING])

      first_of_milestone_func = Feature._first_of_milestone
      if version == 2:
        first_of_milestone_func = Feature._first_of_milestone_v2

      last_good_idx = 0
      for i, ver in enumerate(versions):
        idx = first_of_milestone_func(feature_list, ver, start=last_good_idx)
        if idx != -1:
          feature_list[idx]['first_of_milestone'] = True
          last_good_idx = idx
    except Exception as e:
      logging.error(e)

  def format_for_template(self, version=None):
    d = self.to_dict()

    if version == 2:
      if self.is_saved():
        d['id'] = self.key().id()
      else:
        d['id'] = None
      d['category'] = FEATURE_CATEGORIES[self.category]
      d['created'] = {
        'by': d.pop('created', None),
        'when': d.pop('created_by', None),
      }
      d['updated'] = {
        'by': d.pop('updated_by', None),
        'when': d.pop('updated', None),
      }
      d['standards'] = {
        'spec': d.pop('spec_link', None),
        'status': {
          'text': STANDARDIZATION[self.standardization],
          'val': d.pop('standardization', None),
        },
        'visibility': {
          'text': VISIBILITY_CHOICES[self.visibility],
          'val': d.pop('visibility', None),
        },
        'footprint': {
          'val': d.pop('footprint', None),
          #'text': FOOTPRINT_CHOICES[self.footprint]
        }
      }
      d['resources'] = {
        'samples': d.pop('sample_links', []),
        'docs': d.pop('doc_links', []),
      }
      d['tags'] = d.pop('search_tags', [])
      d['browsers'] = {
        'chrome': {
          'bug': d.pop('bug_url', None),
          'blink_components': d.pop('blink_components', []),
          'owners': d.pop('owner', []),
          'origintrial': self.impl_status_chrome == ORIGIN_TRIAL,
          'intervention': self.impl_status_chrome == INTERVENTION,
          'prefixed': d.pop('prefixed', False),
          'flag': self.impl_status_chrome == BEHIND_A_FLAG,
          'status': {
            'text': IMPLEMENTATION_STATUS[self.impl_status_chrome],
            'val': d.pop('impl_status_chrome', None)
          },
          'desktop': d.pop('shipped_milestone', None),
          'android': d.pop('shipped_android_milestone', None),
          'webview': d.pop('shipped_webview_milestone', None),
          'ios': d.pop('shipped_ios_milestone', None),
        },
        'opera': {
          'desktop': d.pop('shipped_opera_milestone', None),
          'android': d.pop('shipped_opera_android_milestone', None),
        },
        'ff': {
          'view': {
            'text': VENDOR_VIEWS[self.ff_views],
            'val': d.pop('ff_views', None),
            'url': d.pop('ff_views_link', None),
          }
        },
        'edge': {
          'view': {
            'text': VENDOR_VIEWS[self.ie_views],
            'val': d.pop('ie_views', None),
            'url': d.pop('ie_views_link', None),
          }
        },
        'safari': {
          'view': {
            'text': VENDOR_VIEWS[self.safari_views],
            'val': d.pop('safari_views', None),
            'url': d.pop('safari_views_link', None),
          }
        },
        'webdev': {
          'view': {
            'text': WEB_DEV_VIEWS[self.web_dev_views],
            'val': d.pop('web_dev_views', None),
          }
        }
      }

      if self.shipped_milestone:
        d['browsers']['chrome']['status']['milestone_str'] = self.shipped_milestone
      elif self.shipped_milestone is None and self.shipped_android_milestone:
        d['browsers']['chrome']['status']['milestone_str'] = self.shipped_android_milestone
      else:
        d['browsers']['chrome']['status']['milestone_str'] = d['browsers']['chrome']['status']['text']

      del d['created']

      del_none(d) # Further prune response by removing null/[] values.

    else:
      if self.is_saved():
        d['id'] = self.key().id()
      else:
        d['id'] = None
      d['category'] = FEATURE_CATEGORIES[self.category]
      d['visibility'] = VISIBILITY_CHOICES[self.visibility]
      d['impl_status_chrome'] = IMPLEMENTATION_STATUS[self.impl_status_chrome]
      d['meta'] = {
        'origintrial': self.impl_status_chrome == ORIGIN_TRIAL,
        'intervention': self.impl_status_chrome == INTERVENTION,
        'needsflag': self.impl_status_chrome == BEHIND_A_FLAG,
        }
      if self.shipped_milestone:
        d['meta']['milestone_str'] = self.shipped_milestone
      elif self.shipped_milestone is None and self.shipped_android_milestone:
        d['meta']['milestone_str'] = self.shipped_android_milestone
      else:
        d['meta']['milestone_str'] = d['impl_status_chrome']
      d['ff_views'] = {'value': self.ff_views,
                       'text': VENDOR_VIEWS[self.ff_views]}
      d['ie_views'] = {'value': self.ie_views,
                       'text': VENDOR_VIEWS[self.ie_views]}
      d['safari_views'] = {'value': self.safari_views,
                           'text': VENDOR_VIEWS[self.safari_views]}
      d['standardization'] = {'value': self.standardization,
                              'text': STANDARDIZATION[self.standardization]}
      d['web_dev_views'] = {'value': self.web_dev_views,
                            'text': WEB_DEV_VIEWS[self.web_dev_views]}

    return d

  def format_for_edit(self):
    d = self.to_dict()
    #d['id'] = self.key().id
    d['owner'] = ', '.join(self.owner)
    d['doc_links'] = '\r\n'.join(self.doc_links)
    d['sample_links'] = '\r\n'.join(self.sample_links)
    d['search_tags'] = ', '.join(self.search_tags)
    d['blink_components'] = ', '.join(self.blink_components)
    return d

  @classmethod
  def get_all(self, limit=None, order='-updated', filterby=None,
              update_cache=False):
    KEY = '%s|%s|%s' % (Feature.DEFAULT_MEMCACHE_KEY, order, limit)

    # TODO(ericbidelman): Support more than one filter.
    if filterby is not None:
      s = ('%s%s' % (filterby[0], filterby[1])).replace(' ', '')
      KEY += '|%s' % s

    feature_list = memcache.get(KEY)

    if feature_list is None or update_cache:
      query = Feature.all().order(order) #.order('name')

      # TODO(ericbidelman): Support more than one filter.
      if filterby:
        query.filter(filterby[0], filterby[1])

      features = query.fetch(limit)

      feature_list = [f.format_for_template() for f in features]

      memcache.set(KEY, feature_list)

    return feature_list

  @classmethod
  def get_all_with_statuses(self, statuses, update_cache=False):
    if not statuses:
      return []

    KEY = '%s|%s' % (Feature.DEFAULT_MEMCACHE_KEY, sorted(statuses))

    feature_list = memcache.get(KEY)

    if feature_list is None or update_cache:
      # There's no way to do an OR in a single datastore query, and there's a
      # very good chance that the self.get_all() results will already be in
      # memcache, so use an array comprehension to grab the features we
      # want from the array of everything.
      feature_list = [feature for feature in self.get_all(update_cache=update_cache)
                      if feature['impl_status_chrome'] in statuses]
      memcache.set(KEY, feature_list)

    return feature_list

  @classmethod
  def get_feature(self, feature_id, update_cache=False):
    KEY = '%s|%s' % (Feature.DEFAULT_MEMCACHE_KEY, feature_id)
    feature = memcache.get(KEY)

    if feature is None or update_cache:
      unformatted_feature = Feature.get_by_id(feature_id)
      if unformatted_feature:
        feature = unformatted_feature.format_for_template()
        feature['updated_display'] = unformatted_feature.updated.strftime("%Y-%m-%d")
        feature['new_crbug_url'] = unformatted_feature.new_crbug_url()
        memcache.set(KEY, feature)

    return feature

  @classmethod
  def get_chronological(self, limit=None, update_cache=False, version=None):
    KEY = '%s|%s|%s|%s' % (Feature.DEFAULT_MEMCACHE_KEY,
                           'cronorder', limit, version)

    keys = Feature.get_feature_chunk_memcache_keys(KEY)
    feature_list = memcache.get_multi(keys)

    # If we didn't get the expected number of chunks back (or a cache update
    # was requested), do a db query.
    if len(feature_list.keys()) != len(keys) or update_cache:
      # Features with no active, in dev, proposed features.
      q = Feature.all()
      q.order('impl_status_chrome')
      q.order('name')
      q.filter('impl_status_chrome <=', IN_DEVELOPMENT)
      pre_release = q.fetch(None)

      # Shipping features. Exclude features that do not have a desktop
      # shipping milestone.
      q = Feature.all()
      q.order('-shipped_milestone')
      q.order('name')
      q.filter('shipped_milestone !=', None)
      shipping_features = q.fetch(None)

      # Features with an android shipping milestone but no desktop milestone.
      q = Feature.all()
      q.order('-shipped_android_milestone')
      q.order('name')
      q.filter('shipped_milestone =', None)
      android_only_shipping_features = q.fetch(None)

      # No longer pursuing features.
      q = Feature.all()
      q.order('impl_status_chrome')
      q.order('name')
      q.filter('impl_status_chrome =', NO_LONGER_PURSUING)
      no_longer_pursuing_features = q.fetch(None)

      shipping_features.extend(android_only_shipping_features)

      shipping_features = [f for f in shipping_features if (IN_DEVELOPMENT < f.impl_status_chrome < NO_LONGER_PURSUING)]

      def getSortingMilestone(feature):
        feature._sort_by_milestone = (feature.shipped_milestone or
                                      feature.shipped_android_milestone)
        return feature

      # Sort the feature list on either Android shipping milestone or desktop
      # shipping milestone, depending on which is specified. If a desktop
      # milestone is defined, that will take default.
      shipping_features = map(getSortingMilestone, shipping_features)

      # First sort by name, then sort by feature milestone (latest first).
      shipping_features.sort(key=lambda f: f.name, reverse=False)
      shipping_features.sort(key=lambda f: f._sort_by_milestone, reverse=True)

      # Constructor the proper ordering.
      pre_release.extend(shipping_features)
      pre_release.extend(no_longer_pursuing_features)

      feature_list = [f.format_for_template(version) for f in pre_release]

      self._annotate_first_of_milestones(feature_list, version=version)

      # Memcache doesn't support saving values > 1MB. Break up features list into
      # chunks so we don't hit the limit.
      memcache.set_multi(Feature.set_feature_chunk_memcache_keys(KEY, feature_list))
    else:
      temp_feature_list = []
      # Reconstruct feature list by ordering chunks.
      for key in sorted(feature_list.keys()):
        temp_feature_list.extend(feature_list[key])
      feature_list = temp_feature_list

    return feature_list

  @classmethod
  def get_shipping_samples(self, limit=None, update_cache=False):
    KEY = '%s|%s|%s' % (Feature.DEFAULT_MEMCACHE_KEY, 'samples', limit)

    feature_list = memcache.get(KEY)

    if feature_list is None or update_cache:
      # Get all shipping features. Ordered by shipping milestone (latest first).
      q = Feature.all()
      q.filter('impl_status_chrome IN', [ENABLED_BY_DEFAULT, ORIGIN_TRIAL, INTERVENTION])
      q.order('-impl_status_chrome')
      q.order('-shipped_milestone')
      q.order('name')
      features = q.fetch(None)

      # Get non-shipping features (sans removed or deprecated ones) and
      # append to bottom of list.
      q = Feature.all()
      q.filter('impl_status_chrome <', ENABLED_BY_DEFAULT)
      q.order('-impl_status_chrome')
      q.order('-shipped_milestone')
      q.order('name')
      others = q.fetch(None)
      features.extend(others)

      # Filter out features without sample links.
      feature_list = [f.format_for_template() for f in features
                      if len(f.sample_links)]

      memcache.set(KEY, feature_list)

    return feature_list

  def crbug_number(self):
    if not self.bug_url:
      return
    m = re.search(r'[\/|?id=]([0-9]+)$', self.bug_url)
    if m:
      return m.group(1)

  def new_crbug_url(self):
    url = 'https://bugs.chromium.org/p/chromium/issues/entry'
    params = ['components=' + self.blink_components[0] or BlinkComponent.DEFAULT_COMPONENT]
    crbug_number = self.crbug_number()
    if crbug_number and self.impl_status_chrome in (
        NO_ACTIVE_DEV,
        PROPOSED,
        IN_DEVELOPMENT,
        BEHIND_A_FLAG,
        ORIGIN_TRIAL,
        INTERVENTION):
      params.append('blocking=' + crbug_number)
    if self.owner:
      params.append('cc=' + ','.join(self.owner))
    return url + '?' + '&'.join(params)

  def __init__(self, *args, **kwargs):
    super(Feature, self).__init__(*args, **kwargs)

    # Stash existing values when entity is created so we can diff property
    # values later in put() to know what's changed. https://stackoverflow.com/a/41344898
    for prop_name, prop in self.properties().iteritems():
      old_val = getattr(self, prop_name, None)
      setattr(self, '_old_' + prop_name, old_val)

  def __notify_feature_owners_of_changes(self, is_update):
    """Async notifies owners of new features and property changes to features by
       posting to a task queue."""
    # Diff values to see what properties have changed.
    changed_props = []
    for prop_name, prop in self.properties().iteritems():
      new_val = getattr(self, prop_name, None)
      old_val = getattr(self, '_old_' + prop_name, None)
      if new_val != old_val:
        changed_props.append({
            'prop_name': prop_name, 'old_val': old_val, 'new_val': new_val})

    payload = json.dumps({
      'changes': changed_props,
      'is_update': is_update,
      'feature': self.format_for_template(version=2)
    })
    queue = taskqueue.Queue()#name='emailer')
    # Create task to email owners.
    task = taskqueue.Task(method="POST", url='/tasks/email-owners',
        target='notifier', payload=payload)
    queue.add(task)

  def put(self, **kwargs):
    is_update = self.is_saved()
    key = super(Feature, self).put(**kwargs)
    self.__notify_feature_owners_of_changes(is_update)
    return key

  # Metadata.
  created = db.DateTimeProperty(auto_now_add=True)
  updated = db.DateTimeProperty(auto_now=True)
  updated_by = db.UserProperty(auto_current_user=True)
  created_by = db.UserProperty(auto_current_user_add=True)

  # General info.
  category = db.IntegerProperty(required=True)
  name = db.StringProperty(required=True)
  summary = db.StringProperty(required=True, multiline=True)

  # Chromium details.
  bug_url = db.LinkProperty()
  blink_components = db.StringListProperty(required=True, default=[BlinkComponent.DEFAULT_COMPONENT])

  impl_status_chrome = db.IntegerProperty(required=True)
  shipped_milestone = db.IntegerProperty()
  shipped_android_milestone = db.IntegerProperty()
  shipped_ios_milestone = db.IntegerProperty()
  shipped_webview_milestone = db.IntegerProperty()
  shipped_opera_milestone = db.IntegerProperty()
  shipped_opera_android_milestone = db.IntegerProperty()

  owner = db.ListProperty(db.Email)
  footprint = db.IntegerProperty()
  visibility = db.IntegerProperty(required=True)

  #webbiness = db.IntegerProperty() # TODO: figure out what this is

  # Standards details.
  standardization = db.IntegerProperty(required=True)
  spec_link = db.LinkProperty()
  prefixed = db.BooleanProperty()

  ff_views = db.IntegerProperty(required=True, default=NO_PUBLIC_SIGNALS)
  ie_views = db.IntegerProperty(required=True, default=NO_PUBLIC_SIGNALS)
  safari_views = db.IntegerProperty(required=True, default=NO_PUBLIC_SIGNALS)

  ff_views_link = db.LinkProperty()
  ie_views_link = db.LinkProperty()
  safari_views_link = db.LinkProperty()

  # Web dev details.
  web_dev_views = db.IntegerProperty(required=True)
  doc_links = db.StringListProperty()
  sample_links = db.StringListProperty()
  #tests = db.StringProperty()

  search_tags = db.StringListProperty()

  comments = db.StringProperty(multiline=True)


class PlaceholderCharField(forms.CharField):

  def __init__(self, *args, **kwargs):
    #super(forms.CharField, self).__init__(*args, **kwargs)

    attrs = {}
    if kwargs.get('placeholder'):
      attrs['placeholder'] = kwargs.get('placeholder')
      del kwargs['placeholder']

    label = kwargs.get('label') or ''
    if label:
      del kwargs['label']

    self.max_length = kwargs.get('max_length') or None

    super(forms.CharField, self).__init__(label=label,
        widget=forms.TextInput(attrs=attrs), *args, **kwargs)


# class PlaceholderForm(forms.Form):
#   def __init__(self, *args, **kwargs):
#     super(PlaceholderForm, self).__init__(*args, **kwargs)

#     for field_name in self.fields:
#      field = self.fields.get(field_name)
#      if field:
#        if type(field.widget) in (forms.TextInput, forms.DateInput):
#          field.widget = forms.TextInput(attrs={'placeholder': field.label})


class FeatureForm(forms.Form):

  SHIPPED_HELP_TXT = ('First milestone the feature shipped with this status '
                      '(either enabled by default, origin trial, intervention, '
                      'or deprecated)')

  #name = PlaceholderCharField(required=True, placeholder='Feature name')
  name = forms.CharField(required=True, label='Feature')

  summary = forms.CharField(label='', required=True, max_length=500,
      widget=forms.Textarea(attrs={'cols': 50, 'placeholder': 'Summary description', 'maxlength': 500}))

  # owner = PlaceholderCharField(
  #     required=False, placeholder='Owner(s) email',
  #     help_text='Comma separated list of full email addresses (@chromium.org preferred).')

  category = forms.ChoiceField(required=True,
      choices=sorted(FEATURE_CATEGORIES.items(), key=lambda x: x[1]))

  owner = forms.CharField(required=False, label='Owner(s) email',
      help_text='Comma separated list of full email addresses. Prefer @chromium.org.')


  bug_url = forms.URLField(required=False, label='Bug URL',
      help_text='OWP Launch Tracking, crbug, etc.')

  blink_components = forms.ChoiceField(
      required=True,
      label='Blink component',
      help_text='Select the most specific component. If unsure, leave as "%s".' % BlinkComponent.DEFAULT_COMPONENT,
      choices=[(x, x) for x in BlinkComponent.fetch_all_components()],
      initial=[BlinkComponent.DEFAULT_COMPONENT])

  impl_status_chrome = forms.ChoiceField(required=True,
      label='Status in Chromium', choices=IMPLEMENTATION_STATUS.items())

  #shipped_milestone = PlaceholderCharField(required=False,
  #                                         placeholder='First milestone the feature shipped with this status (either enabled by default or experimental)')
  shipped_milestone = forms.IntegerField(required=False, label='',
      help_text='Chrome for desktop: ' + SHIPPED_HELP_TXT)

  shipped_android_milestone = forms.IntegerField(required=False, label='',
      help_text='Chrome for Android: ' + SHIPPED_HELP_TXT)

  shipped_ios_milestone = forms.IntegerField(required=False, label='',
      help_text='Chrome for iOS: ' + SHIPPED_HELP_TXT)

  shipped_webview_milestone = forms.IntegerField(required=False, label='',
      help_text='Chrome for Android web view: ' + SHIPPED_HELP_TXT)

  shipped_opera_milestone = forms.IntegerField(required=False, label='',
      help_text='Opera for desktop: ' + SHIPPED_HELP_TXT)

  shipped_opera_android_milestone = forms.IntegerField(required=False, label='',
      help_text='Opera for Android: ' + SHIPPED_HELP_TXT)

  prefixed = forms.BooleanField(required=False, initial=False, label='Prefixed?')

  standardization = forms.ChoiceField(
      label='Standardization', choices=STANDARDIZATION.items(),
      initial=EDITORS_DRAFT,
      help_text=("The standardization status of the API. In bodies that don't "
                 "use this nomenclature, use the closest equivalent."))

  spec_link = forms.URLField(required=False, label='Spec link',
                             help_text="Prefer editor's draft.")

  doc_links = forms.CharField(label='Doc links', required=False, max_length=500,
      widget=forms.Textarea(attrs={'cols': 50, 'placeholder': 'Links to documentation (one per line)', 'maxlength': 500}),
      help_text='One URL per line')

  sample_links = forms.CharField(label='Samples links', required=False, max_length=500,
      widget=forms.Textarea(attrs={'cols': 50, 'placeholder': 'Links to samples (one per line)', 'maxlength': 500}),
      help_text='One URL per line')

  footprint  = forms.ChoiceField(label='Technical footprint',
      choices=FOOTPRINT_CHOICES.items(), initial=MAJOR_MINOR_NEW_API)

  visibility  = forms.ChoiceField(
      label='Developer visibility',
      choices=VISIBILITY_CHOICES.items(),
      initial=WARRANTS_ARTICLE,
      help_text=('How much press / media / web developer buzz will this '
                 'feature generate?'))

  web_dev_views = forms.ChoiceField(
      label='Web developer views',
      choices=WEB_DEV_VIEWS.items(),
      initial=DEV_NO_SIGNALS,
      help_text=('How positive has the reaction from developers been? If '
                 'unsure, default to "No signals".'))

  safari_views = forms.ChoiceField(label='Safari views',
                                   choices=VENDOR_VIEWS.items(),
                                   initial=NO_PUBLIC_SIGNALS)
  safari_views_link = forms.URLField(required=False, label='',
      help_text='Citation link.')

  ff_views = forms.ChoiceField(label='Firefox views',
                               choices=VENDOR_VIEWS.items(),
                               initial=NO_PUBLIC_SIGNALS)
  ff_views_link = forms.URLField(required=False, label='',
      help_text='Citation link.')

  ie_views = forms.ChoiceField(label='Edge',
                               choices=VENDOR_VIEWS.items(),
                               initial=NO_PUBLIC_SIGNALS)
  ie_views_link = forms.URLField(required=False, label='',
      help_text='Citation link.')

  search_tags = forms.CharField(label='Search tags', required=False,
      help_text='Comma separated keywords used only in search')

  comments = forms.CharField(label='', required=False, max_length=500, widget=forms.Textarea(
      attrs={'cols': 50, 'placeholder': 'Additional comments, caveats, info...', 'maxlength': 500}))

  class Meta:
    model = Feature
    #exclude = ('shipped_webview_milestone',)

  def __init__(self, *args, **keyargs):
    super(FeatureForm, self).__init__(*args, **keyargs)

    meta = getattr(self, 'Meta', None)
    exclude = getattr(meta, 'exclude', [])

    for field_name in exclude:
     if field_name in self.fields:
       del self.fields[field_name]

    for field, val in self.fields.iteritems():
      if val.required:
       self.fields[field].widget.attrs['required'] = 'required'


class AppUser(DictModel):
  """Describes a user for whitelisting."""

  #user = db.UserProperty(required=True, verbose_name='Google Account')
  email = db.EmailProperty(required=True)
  #is_admin = db.BooleanProperty(default=False)
  created = db.DateTimeProperty(auto_now_add=True)
  updated = db.DateTimeProperty(auto_now=True)


class FeatureOwner(DictModel):
  """Describes owner of a web platform feature."""
  created = db.DateTimeProperty(auto_now_add=True)
  updated = db.DateTimeProperty(auto_now=True)
  name = db.StringProperty(required=True)
  email = db.EmailProperty(required=True)
  twitter = db.StringProperty()
  blink_components = db.ListProperty(db.Key)

  def add_as_component_owner(self, component_name):
    """Adds the user to the list of Blink component owners."""
    c = BlinkComponent.get_by_name(component_name)
    if c:
      already_added = len([x for x in self.blink_components if x.id() == c.key().id()])
      if not already_added:
        self.blink_components.append(c.key())
        return self.put()
    return None

  def remove_from_component_owners(self, component_name):
    """Removes the user from the list of Blink component owners."""
    c = BlinkComponent.get_by_name(component_name)
    if c:
      self.blink_components = [x for x in self.blink_components if x.id() != c.key().id()]
      return self.put()
    return None


class HistogramModel(db.Model):
  """Container for a histogram."""

  bucket_id = db.IntegerProperty(required=True)
  property_name = db.StringProperty(required=True)

  @classmethod
  def get_all(self):
    output = {}
    buckets = self.all().fetch(None)
    for bucket in buckets:
      output[bucket.bucket_id] = bucket.property_name
    return output

class CssPropertyHistogram(HistogramModel):
  pass

class FeatureObserverHistogram(HistogramModel):
  pass
