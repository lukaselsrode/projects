

// a 'var' can be overwriten while a 'const' cannot 
var condition=true;
console.log(condition)
console.log('changing condition')
condition=false;
console.log(condition)
// try changing a 'const' type and you'll get an error 
const A=true;
console.log(A)
console.log('changing A')
A=false;




