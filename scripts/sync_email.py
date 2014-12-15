"""
Subscribe all registered OSF users to the 'Open Science Framework General'
mailing list on mailchimp. From the API docs:

1. Grab the users to be updated or created
2. For each user's status, sort them into two batches:
    Users to be subscribed or updated
    Users to be unsubscribed
3. For each of those batches, use:
    listBatchSubscribe() to add new or update existing users on your List
    listBatchUnsubscribe() to remove old users from your List

http://apidocs.mailchimp.com/api/how-to/sync-you-to-mailchimp.php
"""

from modularodm import Q
from framework.auth.core import User
from website import mailchimp_utils, settings
from website.app import init_app
from tests.base import OsfTestCase
from tests.factories import UserFactory, UnconfirmedUserFactory
from nose.tools import *
import mock

import logging
from scripts import utils as script_utils

logger = logging.getLogger(__name__)
GENERAL_LIST = 'Open Science Framework General'

def main():
    script_utils.add_file_logger(logger, __file__)
    # Set up storage backends
    init_app(routes=False)
    users = list(get_users())
    update_users(users)
    subscribe = subscribe_users(users) # confirm list name before running script
    logger.info('{n} users subscribed'.format(n=subscribe['add_count']))

def update_users(users):
    for user in get_users():
        if user.mailing_lists is None:
            user.mailing_lists = {}
        logger.info('User {}\'s mailing_lists dict updated.'.format(user._id))
        user.mailing_lists[GENERAL_LIST] = True
        user.save()

def get_users():
    """Get all users who will be subscribed to the OSF General mailing list."""
    # Exclude unconfirmed and unregistered users
    # NOTE: Unclaimed and unconfirmed users have is_registered=False
    return User.find(Q('is_registered', 'eq', True))


def serialize_user(user):
    """Return the formatted dict expected by the mailchimp batch subscribe endpoint.
    https://apidocs.mailchimp.com/api/2.0/lists/batch-subscribe.php
    """
    return {'email': {'email': user.username}, 'email_type': 'html'}


def subscribe_users(users):
    serialized = [serialize_user(user) for user in users]
    m = mailchimp_utils.get_mailchimp_api()
    list_id = mailchimp_utils.get_list_id_from_name(list_name=GENERAL_LIST)
    return m.lists.batch_subscribe(
            id=list_id,
            batch=serialized,
            double_optin=False,
            update_existing=True
    )


class TestSyncEmail(OsfTestCase):

    @classmethod
    def setUpClass(cls):
        super(TestSyncEmail, cls).setUpClass()
        # Cache real mailchimp API key
        cls._mailchimp_api_key = settings.MAILCHIMP_API_KEY
        # use fake api key for tests
        settings.MAILCHIMP_API_KEY = 'pizza-pie'

    @classmethod
    def tearDownClass(cls):
        super(TestSyncEmail, cls).tearDownClass()
        # restore API key
        settings.MAILCHIMP_API_KEY = cls._mailchimp_api_key
        cls._mailchimp_api_key = None

    def setUp(self):
        super(TestSyncEmail, self).setUp()
        self.user = UserFactory()
        self.unconfirmed = UnconfirmedUserFactory()

    def test_update_users(self):
        users = get_users()
        assert_false(self.user.mailing_lists)

        update_users(users)

        assert_equal(self.user.mailing_lists, {'Open Science Framework General': True})

    def test_serialize_user(self):
        user = UserFactory()
        result = serialize_user(user)
        assert_equal(result, {'email': {'email': user.username}, 'email_type': 'html'})

    def test_get_users(self):
        users = list(get_users())
        assert_equal(len(users), 1)
        assert_not_in(self.unconfirmed, users)
        assert_equal(users, [self.user])

    @mock.patch('website.mailchimp_utils.mailchimp.Lists.list')
    @mock.patch('website.mailchimp_utils.mailchimp.Lists.batch_subscribe')
    def test_subscribe_users_called_with_correct_arguments(self, mock_subscribe, mock_list):
        mock_list.return_value = {'data': [{'id': 1, 'list_name': GENERAL_LIST}]}
        list_id = mailchimp_utils.get_list_id_from_name(GENERAL_LIST)

        users = list(get_users())

        subscribe_users(users)

        serialized = [serialize_user(u) for u in users]
        mock_subscribe.assert_called_with(id=list_id,
                batch=serialized,
                double_optin=False,
                update_existing=True
        )

    @mock.patch('website.mailchimp_utils.mailchimp.Lists.list')
    @mock.patch('website.mailchimp_utils.mailchimp.Lists.batch_subscribe')
    def test_main(self, mock_subscribe, mock_list):
        mock_list.return_value = {'data': [{'id': 1, 'list_name': GENERAL_LIST}]}

        assert_false(self.user.mailing_lists)

        main()

        assert_true(self.user.mailing_lists['Open Science Framework General'])
        mock_subscribe.assert_called


if __name__ == '__main__':
    main()
