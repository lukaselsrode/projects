import os
import kivy
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.popup import Popup
# these are the other modules for the different views
from about import About
from cfg import ConfigureApplication
from measure import ProgramMeasurementApp
# This is for the pop-up to ask if you want to overwrite existing data if the data already exists for todays measurement
from util import new_entry_valid, overwrite_last_entry

# THIS IS THE APPLICATION CONFIG
kivy.logger.Logger.setLevel("DEBUG")
DEFAULT_USER_CFG_PATH = './config/user_data/'
DEFAULT_PROGRAM_VAR_DIR = f'{DEFAULT_USER_CFG_PATH}public'
DEFAULT_IMG = f'{DEFAULT_USER_CFG_PATH}graph.png'
# MAIN BUTTON CFG
MAIN_BUTTON_LAYOUT_SIZE = (1, 0.2)
MAIN_BUTTON_SIZE = (0.25, 1)
MAIN_BUTTON_FONT_SIZE = 30
CFG_BUTTON_COLOR, MEASURE_BUTTON_COLOR = 'red','green'
# VARIABLE CFG BUTTON
CFG_VAR_SIZE_HINT_Y = None
CFG_VAR_HEIGHT = 60
CFG_VAR_FONT_SIZE = 18
CFG_VAR_BUTTON_COLOR = 'orange'

class VariableButton(Button):
    def __init__(self,app, **kwargs):
        super(VariableButton, self).__init__(**kwargs)
        self.size_hint_y, self.height = CFG_VAR_SIZE_HINT_Y, CFG_VAR_HEIGHT
        self.font_size=CFG_VAR_FONT_SIZE
        self.background_color = CFG_VAR_BUTTON_COLOR
        self.app=app
        self.bind(on_release=self.configure_variable)

    def configure_variable(self, instance):
        self.app.close()
        VarConfig=ConfigureApplication(self.text)
        VarConfig.run(),self.app.run()

class VarsDropDown(DropDown):
    def __init__(self,app,vars, **kwargs):
        super(VarsDropDown, self).__init__(**kwargs)
        for v in vars:
            Vbtn = VariableButton(app,text=v)
            self.add_widget(Vbtn)

class MainButton(Button):
    def __init__(self, **kwargs):
        super(MainButton, self).__init__(**kwargs)
        self.size_hint = MAIN_BUTTON_SIZE
        self.font_size= MAIN_BUTTON_FONT_SIZE
        
        
class MainLineGraph(Image):
    def __init__(self, **kwargs):
        super(MainLineGraph, self).__init__(**kwargs)
        self.source = DEFAULT_IMG
        self.fit_mode = 'fill'

class MainButtonLayout(BoxLayout):
    def __init__(self,app,**kwargs):
        super(MainButtonLayout, self).__init__(**kwargs)
        self.app=app
        self.orientation = 'horizontal'
        self.size_hint = MAIN_BUTTON_LAYOUT_SIZE
        # About button
        self.about_button = Button(text='About', size_hint=(0.05, 1),background_color='cyan')
        self.about_button.bind(on_release=self.get_about_page)
        self.add_widget(self.about_button)
        # config options
        self.configure_button = MainButton(text='Configure',background_color=CFG_BUTTON_COLOR)
        self.configure_button.bind(on_press=self.show_cfg_wheel)
        self.add_widget(self.configure_button)
        # measurement options
        self.measure_button = MainButton(text='Measure',background_color=MEASURE_BUTTON_COLOR)
        self.measure_button.bind(on_release=self.measure_prgrm)
        self.add_widget(self.measure_button)

    def get_about_page(self,instance):
        self.app.close()
        TipJar = About()
        TipJar.run()
        self.app.run()
            
    def show_cfg_wheel(self, instance):
        vars = list(map(lambda i: i.split('.')[0], os.listdir(DEFAULT_PROGRAM_VAR_DIR)))
        dropdown = VarsDropDown(self.app,vars)
        dropdown.bind(on_select=lambda instance, x: setattr(self.configure_button, 'text', x))
        dropdown.open(self.configure_button)


    def measure_prgrm(self, instance):
        if new_entry_valid():
            self.start_measurement()
        else:
            self.confirm_overwrite()

    def start_measurement(self):
        self.app.close()
        Measure = ProgramMeasurementApp()
        Measure.run()
        self.app.run()

    def confirm_overwrite(self):
        box = BoxLayout(orientation='vertical', padding=(10))
        msg = Label(text='You have already measured your program today. Do you want to overwrite?')
        btn_layout = BoxLayout(size_hint_y=None, height=30, spacing=10)
        yes_btn = Button(text='Yes', on_release=self.on_confirm)
        no_btn = Button(text='No', on_release=self.on_cancel)
        btn_layout.add_widget(yes_btn)
        btn_layout.add_widget(no_btn)
        box.add_widget(msg)
        box.add_widget(btn_layout)

        self.popup = Popup(title='Confirm Overwrite', content=box,
                           size_hint=(None, None), size=(400, 200),
                           auto_dismiss=False)
        self.popup.open()

    def on_confirm(self, instance):
        self.popup.dismiss()
        overwrite_last_entry()
        self.start_measurement()

    def on_cancel(self, instance):
        self.popup.dismiss()            


class MainPageLayout(BoxLayout):
    def __init__(self,app, **kwargs):
        super(MainPageLayout, self).__init__(**kwargs)
        self.app=app
        self.orientation = 'vertical'
        self.app_title = Label(text='Total Behavioral Tracker',color='blue',pos_hint={'x':0.4,'y':0},size_hint=(0.2,0.2),font_size=45,italic=True)
        self.linegraph, self.main_buttons = MainLineGraph(), MainButtonLayout(self.app)
        self.add_widget(self.app_title)
        self.add_widget(self.linegraph)
        self.add_widget(self.main_buttons)

class MainApp(App):
    def close(self):
        self.root.clear_widgets()
        self.stop()
        
    def build(self):        
        return MainPageLayout(self)

if __name__ == '__main__':
    MainApp().run()
