from santecpro.remote import RemoteScanner

scanner = RemoteScanner("http://192.168.100.103:5000", timeout=1200)

print(scanner.status())

result = scanner.run_stsprocess_scan(
    start_wl=1540,
    stop_wl=1540.1,
    step=0.0001,  # 0.1 pm
    speed=1,
    mpm_module=0,
    mpm_channel=1,
    mpm_range=1,
    csv_name="mac_http_test_small.csv",
    plot=False,
    save_csv="scan_results/mac_http_test_small.csv",
)

print("points:", len(result.wavelengths), len(result.powers))
print("actual_step:", result.scan_params.get("actual_step"))
print("raw_points:", result.scan_params.get("raw_points"))
print("windows_csv:", result.scan_params.get("csv_path"))
