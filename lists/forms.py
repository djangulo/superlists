from django import forms

from lists.models import Item


EMPTY_ITEM_ERROR = "You can't have an empty list item"
UNIQUE_TOGETHER_ERROR = "You've already got this in your list"

class ItemForm(forms.models.ModelForm):

    def save(self, for_list):
        self.instance.list = for_list
        return super().save()

    class Meta:
        model = Item
        fields = ('text',)
        widgets = {
            'text': forms.fields.TextInput(attrs={
                'placeholder': 'Enter a to-do item',
                'class': 'form-control input-lg',
                'autofocus': 'autofocus'
            })
        }
        error_messages = {
            'text': {
                'required': EMPTY_ITEM_ERROR,
                'unique': UNIQUE_TOGETHER_ERROR,
            }
        }
