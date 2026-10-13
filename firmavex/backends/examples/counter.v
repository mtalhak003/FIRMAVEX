// SPDX-License-Identifier: MIT. Self-contained Verilog counter test.
module counter(input clk, input reset, output reg [3:0] count);
 always @(posedge clk) if (reset) count <= 0; else count <= count + 1;
endmodule
module testbench;
 reg clk=0, reset=1;
 wire [3:0] count;
 counter dut(clk,reset,count);
 always #5 clk=~clk;
 initial begin
  $dumpfile("waveform.vcd"); $dumpvars(0,testbench);
  @(negedge clk); reset=0;
  repeat(3) @(negedge clk);
  if(count===3) $display("FIRMAVEX_TEST_RESULT=PASS");
  else $display("FIRMAVEX_TEST_RESULT=FAIL");
  $finish;
 end
endmodule
