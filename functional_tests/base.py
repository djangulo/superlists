import os
import sys
import time

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary

MAX_WAIT = 5

class FunctionalTest(StaticLiveServerTestCase):

    def setUp(self):
        self.launch_browser_instance()
        staging_server = os.environ.get('STAGING_SERVER')
        if staging_server:
            self.live_server_url = 'http://' + staging_server

    def tearDown(self):
        self.browser.refresh()
        self.browser.quit()

    def launch_browser_instance(self):
        if 'win' in sys.platform:
            binary = FirefoxBinary(r'C:\Users\da00440056.USER\Documents\firefox\firefox.exe')
            self.browser = webdriver.Firefox(firefox_binary=binary)
        else:
            self.browser = webdriver.Firefox()
        staging_server = os.environ.get('STAGING_SERVER')
        if staging_server:
            self.live_server_url = 'http://' + staging_server

    def wait_for(self, fn):
        start_time = time.time()
        while True:
            try:
                return fn()
            except (AssertionError, WebDriverException) as error:
                if time.time() - start_time > MAX_WAIT:
                    raise error
                time.sleep(0.5)

    def wait_for_row_in_list_table(self, row_text):
        start_time = time.time()
        while True:
            try:
                table = self.browser.find_element_by_id('id_list_table')
                rows = table.find_elements_by_tag_name('tr')
                self.assertIn(
                    row_text,
                    [row.text for row in rows]
                )
                return
            except (AssertionError, WebDriverException) as error:
                if time.time() - start_time > MAX_WAIT:
                    raise error
                time.sleep(0.5)
