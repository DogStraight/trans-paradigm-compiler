module m;
    `ifndef FEATURE
        wire no_feature;
    `else
        wire has_feature;
    `endif
endmodule
