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
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from util import load_cfg


CFG = load_cfg()['classes']

# Title Label
TITLE=CFG['title']
EXIT = CFG['exit']
POPUP=CFG['popup']

# Page title 
class PageTitle(Label):
    def __init__(self, **kwargs):
        super(PageTitle, self).__init__(**kwargs)
        self.italic = True
        self.pos_hint={'x':0.4,'y':0}
        self.size_hint = TITLE['size']
        self.color = TITLE['color']
        self.font_size = TITLE['font_size']

# Exit button for pages -- THIS IS GOOOOD
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


# Yes No Prompt 
class PopPrompt(Button):
    def __init__(self, prompt, yfunc,nfunc,**kwargs):
        super(PopPrompt, self).__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical', padding=POPUP['padding'])
        self.msg = Label(text=prompt)
        self.btn_layout = BoxLayout(size_hint_y=None, height=POPUP['height'], spacing=POPUP['space'])
        yes_btn = Button(text='Yes', on_release=yfunc,italic=True)
        no_btn = Button(text='No', on_release=nfunc,italic=True)
        self.btn_layout.add_widget(yes_btn)
        self.btn_layout.add_widget(no_btn)
        self.layout.add_widget(self.msg)
        self.layout.add_widget(self.btn_layout)
        self.popup = Popup(content=self.layout,
                            size_hint=(None, None), size=POPUP['size'],
                            auto_dismiss=False)
        self.popup.open() 
    
    def dismiss(self):
        self.popup.dismiss()


