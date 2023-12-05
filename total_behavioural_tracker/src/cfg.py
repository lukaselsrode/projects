from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from kivy.uix.boxlayout import BoxLayout
#from kivy.uix.popup import Popup
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from classes import ExitButton,PageTitle,PopPrompt
from util import update_var_key_data,load_variable_data,load_cfg

CFG = load_cfg()['cfg']

GRID_LAYOUT = CFG['layout']
TEXT = CFG['text']
BUTTONS = CFG['buttons']

VAR_NAME_CFG = TEXT['var']
VAR_EX_CFG = TEXT['explanation']

BTN_HEIGHT = BUTTONS['height']
BTN_FONT_SIZE=BUTTONS['font_size']
ACCEPT_COLOR,LOAD_CFG_COLOR= BUTTONS['accept_color'],BUTTONS['load_color']

INPUT_FONT_SIZE= CFG['input']['font_size']
POPUP_SIZE = CFG['popup']['size']

class ConfigureVarKeyView(GridLayout):
    def __init__(self,file,var,data,app, **kwargs):
        super(ConfigureVarKeyView, self).__init__(**kwargs)
        
        self.app,self.var,self.data,self.file = app,var,data,file # init params
        self.cols, self.padding, self.spacing = GRID_LAYOUT
        # create the exit button 
        self.exit = ExitButton(self.app)
        self.add_widget(self.exit.layout, index=0)
        
        self.config_label = PageTitle(text=var)
        self.add_widget(self.config_label)
        self.config_explanation = Label(text=data['ex'], font_size=VAR_EX_CFG[0],italic=True,color=VAR_EX_CFG[1],valign='middle',halign='center')
        #self.config_explanation = TextBlurb(text=data['ex'],text_size=(None,None))
        self.add_widget(self.config_explanation)

        self.config_input = TextInput(hint_text="Click 'Load' for current config or examples", multiline=True,font_size=INPUT_FONT_SIZE)
        self.add_widget(self.config_input)

        self.button_layout = GridLayout(cols=2, row_force_default=True, row_default_height=BTN_HEIGHT) # UMMMM wha
        
        self.reset_button = Button(text="Load",font_size=BTN_FONT_SIZE,background_color=LOAD_CFG_COLOR,italic=True)
        self.reset_button.bind(on_press=self.reset_default),self.button_layout.add_widget(self.reset_button)

        self.accept_button = Button(text="Accept",font_size=BTN_FONT_SIZE,background_color=ACCEPT_COLOR,italic=True)
        self.accept_button.bind(on_press=self.accept_input),self.button_layout.add_widget(self.accept_button)

        self.add_widget(self.button_layout)

    def reset_default(self, instance):
        display_txt = self.data['default'] if not self.data['user'] else self.data['user']
        self.config_input.text = '\n'.join(list(map(lambda x : x.lower(),display_txt)))
    
    def confirm_new_config(self):
        self.popup = PopPrompt(f"Set {self.var} variable configuration \n for your {self.file.rstrip('.yaml')} ?",self.write_new_config,self.cancel_popup)

    def cancel_popup(self,instance):
        self.popup.dismiss()
        self.app.next_screen()
    
    def write_new_config(self,instance):
        update_var_key_data(self.file,self.var,self.user_input_keys)
        if self.popup: self.popup.dismiss()
        self.app.next_screen()
    # DEBUG:: 
    def accept_input(self, instance):
        self.user_input_keys= list(filter(lambda x: x != '',''.join(list(map(lambda x:x.lower(),self.config_input.text))).split('\n')))
        if not self.user_input_keys and not self.data['user']: self.user_input_keys = self.data['default']
        self.confirm_new_config()

class ConfigureApplication(App):
    def __init__(self,var_file, **kwargs):
        super(ConfigureApplication,self).__init__(**kwargs)
        self.file=var_file
        self.data= load_variable_data(self.file)
        self.vars_list,self.current_var_index = [k for k in self.data.keys()],0
    
    def build(self):
        return self.current_cfg_view()
    
    def current_cfg_view(self):
        var=self.vars_list[self.current_var_index]
        return ConfigureVarKeyView(self.file,var,self.data[var],self)

    def next_screen(self):
        self.current_var_index += 1
        if self.current_var_index < len(self.vars_list):
            self.root.clear_widgets(),self.root.add_widget(self.current_cfg_view())
            return
        self.stop()

