import re
from datetime import datetime
from collections import defaultdict

from newslynx.lib import rss
from newslynx.lib import article
from newslynx.lib import url
from newslynx.sc import SousChef


# check google alerts links.
re_ga_link = re.compile(r'http(s)?://www\.google\.com/url.q=')

# domains to ignore
BAD_DOMAINS = [
    'pastpages',
    'twitter',
    'inagist',
    'facebook'
]


class Feed(SousChef):

    def _fmt(self, obj):
        new = defaultdict()
        for k, v in obj.iteritems():
            if isinstance(v, dict):
                new.update(self._fmt(v))
            else:
                if isinstance(v, list):
                    v = ", ".join([str(vv) for vv in v])
                elif isinstance(v, datetime):
                    v = v.date().isoformat()
                new[k] = v
        return new

    def _is_bad_domain(self, url):
        """
        Should we ignore this alert?
        """
        for d in BAD_DOMAINS + self.org.get('domains', []):
            if d in url:
                return True
        return False

    def format(self, obj):
        """
        For now all of these options are standard to twitter events.
        """
        # set the status.
        obj['status'] = self.options.get('event_status', 'pending')

        # TODO: Make formatting more elegant.
        if self.options.get('set_event_title', None):
            obj['title'] = self.options.get(
                'set_event_title').format(**self._fmt(obj))

        if self.options.get('set_event_description', None):
            obj['description'] = self.options.get(
                'set_event_description').format(**self._fmt(obj))

        if self.options.get('set_event_tag_ids', None) and \
           len(self.options.get('set_event_tag_ids')):

            obj['tag_ids'] = self.options.get('set_event_tag_ids')

        # hack because the app cant handle this field being a list.
        if self.options.get('set_event_content_items', None):
            if 'content_item_ids' not in obj:
                obj['content_item_ids'] = []
            for c in self.options.get('set_event_content_items', []):
                if isinstance(c, dict):
                    if c.get('id', None):
                        obj['content_item_ids'].append(c.get('id'))
                elif isinstance(c, int):
                    obj['content_item_ids'].append(c)
        return obj

    def run(self):

        feed_url = self.options['feed_url']
        feed_domain = url.get_simple_domain(feed_url)

        # iterate through RSS entries.
        for entry in rss.get_entries(feed_url, [feed_domain]):

            # prepare url (these are formatted as redirects).
            entry['url'] = url.prepare(entry['url'],
                                       expand=False, canonicalize=False)

            # ignore bad domains / org's own domains.
            if self._is_bad_domain(entry['url']):
                continue

            # extract and merge article data.
            if url.is_article(entry['url']):
                data = article.extract(entry['url'], type=None)
                if data:
                    entry.update(data)
                    entry.pop('type', None)
                    entry.pop('site_name', None)
                    entry.pop('favicon', None)

            # format and yield.
            entry = self.format(entry)
            yield entry

    def load(self, data):
        """
        Prepare resulting tweets for bulk loading.
        """
        to_post = list(data)
        if len(to_post):
            status_resp = self.api.events.bulk_create(
                data=to_post,
                must_link=self.options.get('must_link'),
                recipe_id=self.recipe_id)
            return self.api.jobs.poll(**status_resp)