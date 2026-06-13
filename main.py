# PyV Compiler — 配置驱动的 Verilog 编译框架
#
# 用法:
#   python main.py pipeline <test_name>   # 运行端到端流水线
#   python main.py -h                      # 帮助

import sys, os

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "pipeline":
        from verilog.run_pipeline import main
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        main()
    else:
        print(__doc__)
