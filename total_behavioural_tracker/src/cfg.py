from kivy.app import App
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from util import update_var_key_data,load_variable_data

GRID_LAYOUT = 1,10,5 # General Grid layout cfg
# CFG for the labels at the top of the view to show what you're configuring 
VAR_NAME_CFG = 40,'yellow'
VAR_EX_CFG = 28,'white'
# Button configurations
BTN_HEIGHT = 80
BTN_FONT_SIZE=30
ACCEPT_COLOR,SH_CONFIG_COLOR='green','blue'
# Text Input configuration
INPUT_FONT_SIZE=18

class ConfigureVarKeyView(GridLayout):
    def __init__(self,file,var,data,app, **kwargs):
        super(ConfigureVarKeyView, self).__init__(**kwargs)
        
        self.app,self.var,self.data,self.file = app,var,data,file # init params
        self.cols, self.padding, self.spacing = GRID_LAYOUT
        # Create an anchor layout for the exit button
        exit_button_layout = AnchorLayout(anchor_x='right', anchor_y='top', size_hint=(1, 0.1))
        exit_button = Button(text='Back', size_hint=(0.1, 1),background_color='red')
        exit_button.bind(on_release=self.exit_app)
        exit_button_layout.add_widget(exit_button)
        self.add_widget(exit_button_layout, index=0)

        self.config_label = Label(text=var,font_size=VAR_NAME_CFG[0],italic=True,color=VAR_NAME_CFG[1])
        self.add_widget(self.config_label)

        self.config_explanation = Label(text=data['ex'], font_size=VAR_EX_CFG[0],italic=True,color=VAR_EX_CFG[1])
        self.add_widget(self.config_explanation)

        self.config_input = TextInput(hint_text="Click 'Load' for current config or examples", multiline=True,font_size=INPUT_FONT_SIZE)
        self.add_widget(self.config_input)

        self.button_layout = GridLayout(cols=2, row_force_default=True, row_default_height=BTN_HEIGHT) # UMMMM wha
        
        self.reset_button = Button(text="Load",font_size=BTN_FONT_SIZE,background_color=SH_CONFIG_COLOR)
        self.reset_button.bind(on_press=self.reset_default),self.button_layout.add_widget(self.reset_button)

        self.accept_button = Button(text="Accept",font_size=BTN_FONT_SIZE,background_color=ACCEPT_COLOR)
        self.accept_button.bind(on_press=self.accept_input),self.button_layout.add_widget(self.accept_button)

        self.add_widget(self.button_layout)

    def exit_app(self, instance):
        self.app.stop()

    def reset_default(self, instance):
        display_txt = self.data['default'] if not self.data['user'] else self.data['user']
        self.config_input.text = '\n'.join(list(map(lambda x : x.lower(),display_txt)))
    
    # TODO: add a pop-up here if there is already a set configuration for 'user' key in config for that config var    
    def accept_input(self, instance):
        
        user_input_keys= list(filter(lambda x: x != '',''.join(list(map(lambda x:x.lower(),self.config_input.text))).split('\n')))
        update_var_key_data(self.file,self.var,user_input_keys)
        
        self.app.next_screen()

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
