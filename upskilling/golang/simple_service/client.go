package main

import (
	"bufio"
	"fmt"
	"log"
	"net"
	"os"
	"strings"
)

const (
	serverAddr = "localhost:8080"
)

func main() {
	// Connect to the server
	conn, err := net.Dial("tcp", serverAddr)
	if err != nil {
		log.Fatalf("Failed to connect to server: %v", err)
	}
	defer conn.Close()

	fmt.Printf("Connected to server at %s\n", serverAddr)
	fmt.Println("Type 'exit' to quit")

	// Read user input and send to server
	reader := bufio.NewReader(os.Stdin)
	for {
		// Get input from user
		fmt.Print("Enter message: ")
		message, err := reader.ReadString('\n')
		if err != nil {
			log.Printf("Error reading input: %v", err)
			continue
		}

		// Remove newline and check for exit command
		message = strings.TrimSpace(message)
		if message == "exit" {
			break
		}

		// Send message to server
		_, err = conn.Write([]byte(message + "\n"))
		if err != nil {
			log.Printf("Error sending message: %v", err)
			continue
		}

		// Read response from server
		reply := make([]byte, 1024)
		n, err := conn.Read(reply)
		if err != nil {
			log.Printf("Error reading response: %v", err)
			continue
		}

		// Print server response
		fmt.Printf("Server reply: %s\n", string(reply[:n]))
	}

	fmt.Println("Client exiting...")
}
