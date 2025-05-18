package main

import (
	"bufio"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"
)

func main() {
	target := "localhost"
	var wg sync.WaitGroup

	for port := 0; port <= 10000; port++ {
		wg.Add(1)
		go func(port int) {
			defer wg.Done()
			address := fmt.Sprintf("%s:%d", target, port)
			conn, err := net.DialTimeout("tcp", address, 5*time.Second)
			if err == nil {
				fmt.Printf("Port %d is open\n", port)
				defer conn.Close()

				// Attempt discovery by reading data from the open port
				conn.SetReadDeadline(time.Now().Add(2 * time.Second))
				reader := bufio.NewReader(conn)
				response, err := reader.ReadString('\n')
				if err == nil {
					fmt.Printf("Received response from port %d: %s\n", port, response)
				} else {
					fmt.Printf("No response from port %d\n", port)
				}
				getProcessInfo(port)
			}
		}(port)
	}

	wg.Wait()
}

// getProcessInfo gets process information for a given port using native Go functionality
func getProcessInfo(port int) {
	// Use netstat to find the process listening on the port
	// This is a cross-platform approach using netstat
	netstatCmd := exec.Command("netstat", "-tulnp")
	output, err := netstatCmd.CombinedOutput()
	if err != nil {
		fmt.Printf("Error running netstat: %v\n", err)
		return
	}

	// Parse netstat output to find the process using the port
	lines := strings.Split(string(output), "\n")
	portStr := fmt.Sprintf(":%d ", port)

	for _, line := range lines {
		if strings.Contains(line, portStr) && strings.Contains(line, "LISTEN") {
			fields := strings.Fields(line)
			if len(fields) < 7 {
				continue
			}

			// The process ID is typically the last field in the format "1234/process"
			pidProcess := fields[6]
			pidStr := strings.Split(pidProcess, "/")[0]
			pid, err := strconv.Atoi(pidStr)
			if err != nil {
				fmt.Printf("Could not parse PID from: %s\n", pidProcess)
				continue
			}

			// Get process details using os.FindProcess
			_, err = os.FindProcess(pid)
			if err != nil {
				fmt.Printf("Could not find process with PID %d: %v\n", pid, err)
				continue
			}

			// Get process name and command line
			exePath, err := os.Readlink(fmt.Sprintf("/proc/%d/exe", pid))
			cmdLine, cmdErr := os.ReadFile(fmt.Sprintf("/proc/%d/cmdline", pid))

			fmt.Printf("Process listening on port %d:\n", port)
			fmt.Printf("  PID: %d\n", pid)

			if err == nil {
				fmt.Printf("  Path: %s\n", exePath)
				fmt.Printf("  Name: %s\n", filepath.Base(exePath))
			}

			if cmdErr == nil {
				cmdArgs := strings.ReplaceAll(string(cmdLine), "\x00", " ")
				fmt.Printf("  Command: %s\n", cmdArgs)
			}

			// Get process status
			status, statusErr := os.ReadFile(fmt.Sprintf("/proc/%d/status", pid))
			if statusErr == nil {
				statusLines := strings.Split(string(status), "\n")
				for _, line := range statusLines {
					if strings.HasPrefix(line, "Name:") || strings.HasPrefix(line, "PPid:") ||
						strings.HasPrefix(line, "State:") || strings.HasPrefix(line, "Threads:") {
						fmt.Printf("  %s\n", line)
					}
				}
			}

			return
		}
	}

	fmt.Printf("No process found listening on port %d\n", port)
}
