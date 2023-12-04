# Copyright 2023 wolfy
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from kivy.uix.button import Button
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from util import load_cfg


CFG = load_cfg()['classes']

# Title Label
TITLE=CFG['title']
TXT=CFG['txt']
EXIT = CFG['exit']


# Page title 
class PageTitle(Label):
    def __init__(self, **kwargs):
        super(PageTitle, self).__init__(**kwargs)
        self.italic = True
        self.pos_hint={'x':0.4,'y':0}
        self.size_hint = TITLE['size']
        self.color = TITLE['color']
        self.font_size = TITLE['font_size']

# Text Blurb
class TextBlurb(Label):
    def __init__(self, **kwargs):
        super(TextBlurb, self).__init__(**kwargs)
        self.halign,self.valign = 'center','middle'
        self.text_size = self.width, None
        self.font_size = TXT['font_size']
        self.color = TXT['color']

class ExitButton(Button):
    def __init__(self,application, **kwargs):
        super(ExitButton, self).__init__(**kwargs)
        self.app = application
        self.layout = AnchorLayout(anchor_x='right', anchor_y='top', size_hint=EXIT['lsize'])
        self.button = Button(text='Back', size_hint=EXIT['bsize'],background_color=EXIT['bcolor'])
        self.button.bind(on_release=self.exit_app)
        self.layout.add_widget(self.button)

    def exit_app(self, instance):
        self.app.stop()



"""

# Pop-up button
box = BoxLayout(orientation='vertical', padding=(10))
msg = Label(text=f"Set {self.var} variable configuration \n for your {self.file.rstrip('.yaml')} ?")
btn_layout = BoxLayout(size_hint_y=None, height=30, spacing=10)
yes_btn = Button(text='Yes', on_release=self.write_new_config,italic=True)
no_btn = Button(text='No', on_release=self.cancel_popup,italic=True)
btn_layout.add_widget(yes_btn)
btn_layout.add_widget(no_btn)
box.add_widget(msg)
box.add_widget(btn_layout)
self.popup = Popup(title=f'{self.var} confirmation', content=box,
                    size_hint=(None, None), size=POPUP_SIZE,
                    auto_dismiss=False)
self.popup.open() 



# Two button layout 
self.button_layout = GridLayout(cols=2, row_force_default=True, row_default_height=BTN_HEIGHT) # UMMMM wha
self.reset_button = Button(text="Load",font_size=BTN_FONT_SIZE,background_color=LOAD_CFG_COLOR,italic=True)
self.reset_button.bind(on_press=self.reset_default),self.button_layout.add_widget(self.reset_button)
self.accept_button = Button(text="Accept",font_size=BTN_FONT_SIZE,background_color=ACCEPT_COLOR,italic=True)
self.accept_button.bind(on_press=self.accept_input),self.button_layout.add_widget(self.accept_button)

"""