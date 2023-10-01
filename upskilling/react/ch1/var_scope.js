// Variable scope, is strange in JS type 'var' is scoped within curly braces {} but not within if/else statements
var A="JS";
var B="JS";


// educated guess from C
if (A || B) {
        var A = "React";
        let B = "React";
	// notice how cahnging 'var' in this code block changes global var but 'let' does not
        console.log("code_block A:",A,'\n',"code_block B:",B);
}
console.log("global A:",A,'\n',"global B:",B)

// the same is true of variables in for loops

var div,container=document.getElementById("container");
for (var i=0; i<5;i++){
	div = document.createElement("div");
	div.onclick=function() {alert("this is box #"+ i);}
	container.appendChild(div);
}

