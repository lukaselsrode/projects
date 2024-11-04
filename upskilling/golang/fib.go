// usage : $ go run fib.go <number>
package main

import (
    "fmt"
    "os"
    "strconv"
    "math/big"
)

func fibDoubling(n int) *big.Int {
    if n == 0 {
        return big.NewInt(0)
    }
    a, b := big.NewInt(0), big.NewInt(1) // F(0) = 0, F(1) = 1
    fibHelper(n, a, b)
    return a
}

// Recursive helper function that computes (F(n), F(n+1))
func fibHelper(n int, a, b *big.Int) {
    if n == 0 {
        a.SetInt64(0)
        b.SetInt64(1)
        return
    }

    // Recursively calculate F(k) and F(k+1) where k = n / 2
    c, d := new(big.Int), new(big.Int)
    fibHelper(n/2, c, d)

    // a = F(2k) = F(k) * [2*F(k+1) - F(k)]
    temp1 := new(big.Int).Lsh(d, 1) // temp1 = 2 * F(k+1)
    temp1.Sub(temp1, c)             // temp1 = 2*F(k+1) - F(k)
    a.Mul(c, temp1)                 // a = F(k) * (2*F(k+1) - F(k))

    // b = F(2k+1) = F(k+1)^2 + F(k)^2
    temp2 := new(big.Int).Mul(d, d) // temp2 = F(k+1)^2
    temp3 := new(big.Int).Mul(c, c) // temp3 = F(k)^2
    b.Add(temp2, temp3)             // b = F(k+1)^2 + F(k)^2

    // If n is odd, set (a, b) = (b, a + b)
    if n%2 != 0 {
        aCopy := new(big.Int).Set(a) // Copy a before modifying
        a.Set(b)                     // Set a to b
        b.Add(b, aCopy)              // Set b to b + aCopy (original a)
    }
}

func main() {
    if len(os.Args) < 2 {
        fmt.Println("Please provide an argument")
        return
    }

    arg, err := strconv.Atoi(os.Args[1])
    if err != nil {
        fmt.Println("Invalid argument, please provide a valid integer")
        return
    }

    res := fibDoubling(arg)
    fmt.Printf("Fibonacci Number of %d is : %d\n", arg ,res)
}
