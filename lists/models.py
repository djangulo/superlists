from django.core.urlresolvers import reverse
from django.db import models


class List(models.Model):

    def get_absolute_url(self):
        return reverse('lists:view', args=[self.id])


class Item(models.Model):
    text = models.TextField(default='')
    list = models.ForeignKey('List', default=None)

