package main

import (
	"bufio"
	"fmt"
	"os"
	"strings")


func is_borderline(string:mtype) {
	if !(strings.Contains(mtype,"(")) && !(strings.Contains(mtype,")"))
	{return false} else {return true}
}


func main() {
	fmt.Printf("Enter your MBTI Personality Type: \n \t\t NOTE: if borderline defined enter '(E/I)NTP'\n")
	input := bufio.NewScanner(os.Stdin)
	for input.Scan() {
		if is_borderline(input.Text()) {fmt.Printf("MBTI is borderline: %s\n",mtype)}
		else{fmt.Printf("MBTI is: %s\n",mtype)} 
	}
}



