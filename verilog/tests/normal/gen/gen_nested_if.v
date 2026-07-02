// Test: nested single-statement if-else
module nested_if_test (
input wire a, b, c
,
output reg x, y
) ;
always @ ( * ) begin
if ( a )
if ( b )
x = 1'b1;
if ( a )
if ( b )
x = 1'b1;
else
y = 1'b0;
if ( a ) begin
if ( b ) x = 1'b1 ;
end else begin