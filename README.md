# Lexis Bulk API

This library provides a Python wrapper around the Lexis Nexis Bulk API to make it easier for users to fetch data from the API endpoints.

## API Overview

The official Lexis Nexis Bulk API docs are available here (note you'll need to request access to the Lexis Nexis Developer Documentation to see these):
https://www.lexisnexis.com/lextalk/developers/ln-bulk-api/p/bulkapidocs.aspx

The Lexis Nexis Bulk API represents documents in
a tree-like fashion. The top level nodes in this tree are the "source sets" (essentially publication titles) that your institution has purchased or licensed. Each source set has one or more "subscriptions", and each "subscription" has one or more "files", where a file contains information about one or more "documents" (XML files that end users will consume). Each "document" has multiple states, where each state describes the content of the file at a given point in time.

Graphically, the tree looks like this:

```bash
- source_set
  - subscription
    - file
      - document
        - state
```

## Usage

To use this library to collect data from the Lexis Nexis Bulk API, one should first install this library as follows:

```bash
pip install lexis_bulk_api
```

Then in one can create an API session and begin downloading data with the following:

```python
from lexis_bulk_api import Session

key = 'YOUR_BULK_API_KEY'
secret = 'YOUR_BULK_API_SECRET'
session = Session(client_key=key, client_secret=secret)
```

After creating a session, you can get all source sets to which your account has access:

```python
# get all source sets to which your account has access
source_sets = session.get_source_sets()
```

Let's find the globally-unique identifier (guid) for the first source set in that list:

```python
subscription_guids = session.get_subscription_guids(source_sets[0])
```

Next let's get the subscriptions that belong to the first subscription guid:

```python
subscriptions = session.get_subscription(subscription_guids[0])
```

Let's find the guids for the files in that subscription:

```python
file_guids = session.get_file_guids(subscriptions)
```

Now let's get the first file from that subscription. Note we must pass in the subscription guid and the file guid to the API endpoint, and the response comes in chunks as a single "file" object can contain more data than can fit in RAM concurrently:

```python
for text in session.get_file(file_guids[0], subscription_guids[0]):
  print(text)
```

Each `text` instance will contain one block of text from the current file.