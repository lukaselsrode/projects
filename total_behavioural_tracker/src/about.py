from webbrowser import open_new_tab as urlopen
from kivy.uix.anchorlayout import AnchorLayout
from kivy.app import App
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label


# TODO: NEED TO PUT THE CFG VALS UP HERE AT SOME POINT YEAH ? 


class HyperlinkLabel(Label):
    def __init__(self, **kwargs):
        super(HyperlinkLabel, self).__init__(**kwargs)
        self.markup = True

    def on_ref_press(self, ref):
        print(f'Opening {ref} ...')
        urlopen(ref)

class About(App):
    def build(self):
        layout = BoxLayout(orientation='vertical')
        # exit button
        exit_button_layout = AnchorLayout(anchor_x='right', anchor_y='top', size_hint=(1, 0.1))
        exit_button = Button(text='Exit', size_hint=(0.1, 1),background_color='red')
        exit_button.bind(on_release=self.exit_app)
        exit_button_layout.add_widget(exit_button)
        layout.add_widget(exit_button_layout, index=0)
        # Title 
        title_label = Label(text='About Total Behavioral Tracker', font_size='20sp')
        # The links 
        hyperlink_text = HyperlinkLabel(text='[ref=https://linkedin.com/]Linkedin[/ref]\n[ref=http://example.com]Example 2[/ref]')
        # need 3 links: 
        #   1. link to the amazon book 
        #   2. link to the codebase 
        #   3. link to a tipjar
        layout.add_widget(title_label)
        layout.add_widget(hyperlink_text)
        return layout 

    def exit_app(self, instance):
        self.stop()
        

if __name__ == '__main__':
    About().run()
