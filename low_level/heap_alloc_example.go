// go run heap_alloc_example.go

package main

import (
	"fmt"
	"runtime"
	"strings"
	"unsafe"
)

func printMemStats(prefix string) {
	var m runtime.MemStats
	runtime.ReadMemStats(&m)
	fmt.Printf("%s:\n", prefix)
	fmt.Printf("  Alloc = %v MiB\n", bToMb(m.Alloc))
	fmt.Printf("  TotalAlloc = %v MiB\n", bToMb(m.TotalAlloc))
	fmt.Printf("  Sys = %v MiB\n", bToMb(m.Sys))
	fmt.Printf("  NumGC = %v\n", m.NumGC)
	fmt.Printf("  HeapAlloc = %v MiB\n", bToMb(m.HeapAlloc))
	fmt.Printf("  HeapSys = %v MiB\n", bToMb(m.HeapSys))
}

func bToMb(b uint64) uint64 {
	return b / 1024 / 1024
}

func main() {
	input := strings.Repeat(" ", 8*1024*1024)

	printMemStats("Initial memory stats")

	// Force the string to be allocated on the heap
	heapString := new(string)
	*heapString = input

	// Print memory information
	fmt.Printf("\nPointer variable address: %p\n", &heapString)
	fmt.Printf("Heap-allocated string pointer: %p\n", heapString)
	fmt.Printf("String data starts at: %p\n", unsafe.StringData(*heapString))

	runtime.GC()
	printMemStats("\nAfter allocating string on heap")

	fmt.Printf("\nString size: %d bytes\n", unsafe.Sizeof(*heapString)+uintptr(len(*heapString)))
	printMemStats("\nBefore clearing reference")
	// deref and clear reference
	heapString = nil
	runtime.GC()
	printMemStats("\nAfter clearing reference and running GC")
}
