package main

import (
	"bufio"
	"fmt"
	"io"
	"log"
	"net"
	"os/exec"
	"strings"
	"time"
)

const (
	port = "8080"
)

func handleConnection(conn net.Conn) {
	defer conn.Close()
	reader := bufio.NewReader(conn)

	for {
		// Read the request
		message, err := reader.ReadString('\n')
		if err != nil {
			if err != io.EOF {
				log.Printf("Error reading: %v", err)
			}
			return
		}

		// Remove the newline character
		message = strings.TrimSpace(message)
		log.Printf("Received: %s", message)

		// Send the request back to the client
		_, err = fmt.Fprintf(conn, "%s\n", message)
		if err != nil {
			log.Printf("Error writing: %v", err)
			return
		}
	}
}

func isPortInUse(port string) bool {
	conn, err := net.DialTimeout("tcp", ":"+port, time.Second)
	if err == nil {
		conn.Close()
		return true
	}
	return false
}

func killProcessOnPort(port string) error {
	cmd := exec.Command("lsof", "-t", fmt.Sprintf("-i:%s", port))
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("no process found on port %s", port)
	}

	pid := strings.TrimSpace(string(output))
	if pid == "" {
		return fmt.Errorf("no process found on port %s", port)
	}

	killCmd := exec.Command("kill", "-9", pid)
	if err := killCmd.Run(); err != nil {
		return fmt.Errorf("failed to kill process %s: %v", pid, err)
	}

	time.Sleep(1 * time.Second) // Give the OS time to release the port
	return nil
}

func main() {
	// Check if port is in use and try to kill the process if it is
	if isPortInUse(port) {
		log.Printf("Port %s is in use, attempting to restart the server...", port)
		if err := killProcessOnPort(port); err != nil {
			log.Fatalf("Failed to free port %s: %v", port, err)
		}
	}

	// Start TCP server
	listener, err := net.Listen("tcp", ":"+port)
	if err != nil {
		log.Fatalf("Failed to start server: %v", err)
	}
	defer listener.Close()

	log.Printf("TCP Echo Server is running on port %s...", port)

	for {
		// Accept new connections
		conn, err := listener.Accept()
		if err != nil {
			log.Printf("Error accepting connection: %v", err)
			continue
		}

		// Handle the connection in a new goroutine
		go handleConnection(conn)
	}
}
