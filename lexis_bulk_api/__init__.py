from bs4 import BeautifulSoup
from collections import defaultdict
import xmltodict
import functools
import requests
import base64
import uuid
import json
import re
import os

out_dir = 'output'

class Session:
  def __init__(self, *args, **kwargs):
    self.api_host = kwargs.get('api_host', 'content-api.lexisnexis.com') # api host address
    self.access_token = self.get_access_token(**kwargs)

  ##
  # Authentication
  ##

  def get_access_token(self, client_key='', client_secret=''):
    '''
    Return an authentication token for the user's client key and secret
    '''
    # the data vals will be url encoded in the post request below
    data = {
      'grant_type': 'client_credentials',
      'scope': 'http://oauth.lexisnexis.com/all',
      'format': 'json',
    }
    # these headers encode the authorization credentials
    headers = {
      'X-LN-Request': self.get_lexis_header(),
      'Content-Type': 'application/x-www-form-urlencoded',
      'Authorization': 'Basic ' + base64.b64encode((client_key + ':' + client_secret).encode('utf8')).decode('utf8'),
    }
    # make a request for an "access token"
    r = json.loads(requests.post('https://auth-api.lexisnexis.com/oauth/v2/token', data=data, headers=headers).text)
    # return the access token
    return r['access_token']

  ##
  # Source Sets
  ##

  def get_source_sets(self):
    '''
    Return a list of all source sets
    '''
    return self.get('sourceset').get('sourceSets', {}).get('sourceSet', [])

  ##
  # Subscriptions
  ##

  def get_subscriptions_guids(self, source_sets):
    '''
    Given the response from self.get_source_sets, return a list of
    subscription guids found in that source set
    '''
    guids = []
    for idx, i in enumerate(source_sets):
      guids += self.get_subscription_guid(i)
    return guids

  def get_subscription_guids(self, source_set):
    '''
    Given a member from the array returned by self.get_source_sets, return
    the subscription guid(s) for that source_set
    '''
    if 'subscription' not in source_set: return []
    s = source_set['subscription']
    l = s if isinstance(s, list) else [s]
    guids = []
    for i in l:
      try:
        guids.append(i['guid'])
      except Exception as exc:
        sid = i.get('sourceSetIdentifier', '')
        print(' ! warning: source set {} could not be processed'.format(sid))
    return guids

  def get_subscription(self, guid, start_epoch=0):
    '''
    Given a subscription guid, return the full subscription object
    '''
    return self.get('subscription/{}?startEpoch={}'.format(guid, start_epoch))

  ##
  # Files
  ##

  def get_file_guids(self, subscription):
    '''
    Given the response from self.get_subscription(), return the file guids in
    that subscription
    '''
    guids = []
    for idx, i in enumerate(subscription['subscription']['epochs']['epoch']):
      l = i if isinstance(i, list) else [i]
      for j in l:
        try:
          guids.append(j['link']['@href'].split('/')[-1])
        except Exception as exc:
          print(' ! warning: subscription epoch index {} could not be processed'.format(idx))
    return guids

  def get_file(self, file_guid, subscription_guid, write=False, out_dir='output'):
    '''
    Given a file guid (returned by get_subscription()) and that file's parent
    subscription guid (required by API even though it should be an internal lookup),
    return the full text content from the given file.
    '''
    if write and not os.path.exists(out_dir):
      os.makedirs(out_dir)
    offset = 0
    total = 0
    while True:
      headers = self.get_headers({
        'Accept': 'application/x-bulk-multipart+xml; version=1.0',
        'Content-Type': 'application/x-bulk-multipart+xml; version=1.0',
        'X-LN-Bulk-File': '<FileData><offset>{}</offset><subscriptionGUID>{}</subscriptionGUID></FileData>'.format(offset, subscription_guid),
      })
      url = self.get_url('file/{}'.format(file_guid))
      r = requests.get(url, headers=headers)
      if not r.text: return
      if write:
        path = os.path.join(out_dir, '{}-{}-{}.txt'.format(subscription_guid, file_guid, offset))
        with open(path, 'w') as out:
          out.write(r.text)
      else:
        yield r.text
      # check the response headers for additional pages of data
      meta_headers = r.headers.get('X-LN-Bulk-File', '')
      if meta_headers:
        meta_headers = json.loads(json.dumps(xmltodict.parse(meta_headers)))
        total = meta_headers.get('FileData', {}).get('size')
        offset = meta_headers.get('FileData', {}).get('offset')
        print(' * processed offset', offset, 'of', total)
        if not meta_headers.get('FileData', {}).get('moreDataAvailable'):
          return

  def get_file_changes(self, file):
    '''
    Identify the set of changes outlined in `file`
    NB: PCSI is another term for subscription id, which is another term for
      the source id in the former Lexis Nexis Web Services Kit

    The following notes from LN indicate all possible action types:
      Add – This is a new entry as far as the publisher is concerned. The subscriber should add it. If it already thinks it has it, something has gone wrong (or it is arbitrating between two identical streams of the same content and it can process this as if were a Change)
      Change – This is a change to an entry as far as the publisher is concerned. The entire document (every element / attribute) is included regardless of what actually changed. If the subscriber does not have the old record/transaction, it should process as an Add.
      Delete – This is a mandatory deletion of an entry from all systems. Deleting the identified data item is not optional. As a rule, Masters should not delete data; they should set appropriate attributes in the data to indicate that it has been "sunset". Therefore, when a master uses the Delete action, the likely case is that we are no longer licensed for the data or some other Compliance issue forces us to delete it from our stores. (Principle 4: Compliance) (ref 4)
      Replace – This action is generally used to instruct subscribers that one or more previously published data items were duplicates and should be replaced with an authoritative copy. Further details can be found in the Replace/Remove Extension section of this page.
      Remove – This action is generally used to instruct subscribers that a previously published data item MUST be removed from its purposed copy. Unlike delete a remove expresses additional semantics that MAY be meaningful to some subscribers. Further details can be found in the Replace/Remove Extension section of this page.

    @args:
      file: str the text content of a "file" response from the Bulk API
    @returns:
      dict
        guid: str the guid for an article-level text document
          action_type: str the type of action required for this file (add/edit/delete)
          content: str the full text content for this file
          out_dir: str the path to the directory where this file will be stored on disk
    '''
    d = defaultdict(lambda: defaultdict())
    chunks = [i.strip() for i in file.split('\n\r')]
    # the first block of text is special - it outlines all action types
    for i in BeautifulSoup(chunks[1], 'lxml').find_all('entry'):
      guid = i.find('id').get_text().replace('urn:contentItem:', '')
      action = i.find('lnpub:action').get_text()
      subscription_id = i.find('lnpub:entrymeta')['pcsi']
      d[guid]['action_type'] = action
      d[guid]['subscription_id'] = subscription_id
      d[guid]['out_dir'] = os.path.join(out_dir, 'subscriptions', subscription_id)
    # map each file guid to the full text content
    for i in range(2, len(chunks)-1, 1):
      if (i%2) != 0: continue
      guid = chunks[i].split('urn:contentItem:')[1].split('@lexisnexis.com')[0]
      text = chunks[i+1].strip()
      d[guid]['text'] = text
    return d

  def process_file_changes(self, d):
    '''
    Given a dictionary describing changes to be made, save those changes to disk
    '''
    print('NB: Only add changes will be processed')
    for i in d:
      out_dir = d[i]['out_dir']
      out_path = os.path.join(out_dir, i)
      if not os.path.exists(out_dir): os.makedirs(out_dir)
      # take the appropriate action
      if d[i]['action_type'] == 'add':
        if d[i].get('text', False):
          with open(out_path, 'w') as out: out.write(d[i]['text'])
        else:
          print(' ! warning: file {} does not have a text attribute'.format(i))
      else:
        out_dir = 'unprocessed'
        out_path = os.path.join(out_dir, i + '.json')
        with open(out_path, 'w') as out:
          json.dump(d[i], out)

  ##
  # Helpers
  ##

  def get_lexis_header(self):
    return re.sub('\s+', '', '''
      <rt:requestToken xmlns:rt="http://services.lexisnexis.com/xmlschema/request-token/1">
        <transactionID>{}</transactionID>
        <sequence>1</sequence>
        <featurePermID></featurePermID>
        <clientID>-1</clientID>
        <cpmFeatureCode>22</cpmFeatureCode>
      </rt:requestToken>
    '''.format(str(uuid.uuid1())))

  def get(self, url, headers={}, dtype=dict):
    '''
    Make an API call to a route on {self.api_host}/bulkweb/ and return JSON with the result
    '''
    r = requests.get(self.get_url(url), headers=self.get_headers(headers))
    if dtype == dict:
      return self.xml_to_json(r.text) if r.text else {}
    else:
      return r.text

  def get_url(self, url):
    '''
    Return the URL for an endpoint
    '''
    return 'https://{}/bulkweb/{}'.format(self.api_host, url)

  def get_headers(self, obj):
    '''
    Return a dictionary of headers, and use any key/value pairs in dict `obj` to override the stock headers
    '''
    headers = {
      'Host': self.api_host,
      'X-LN-Request': self.get_lexis_header(),
      'Authorization': 'Bearer ' + self.access_token,
    }
    headers.update(obj)
    return headers

  def xml_to_json(self, xml):
    '''
    Given an XML string return JSON with the same format
    '''
    return json.loads(json.dumps(xmltodict.parse(xml)))

  ##
  # Bulk data delivery methods
  ##

  def parse_s3_data(self, root_dir):
    '''
    Given the path to the root directory with S3 content, process that initial
    data delivery to identify the latest epoch of each subscription and to
    create a mapping from file guid to subscription id and path on disk
    '''
    files = glob2.glob(os.path.join(root_dir, '**'))
    # from this mass of files, find only those with guid paths
    guid_files = [i for i in files if os.path.basename(i).count('-') == 4]
    for i in guid_files:
      with open(i) as f:
        d = self.get_file_changes(f.read())
        self.process_file_changes(d)