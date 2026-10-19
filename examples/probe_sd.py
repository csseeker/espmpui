"""
Diagnostic tool to probe, detect, and benchmark an SD card on ESP32 / ESP32-S3.
Specifically optimized for the Freenove ESP32-S3 CAM onboard MicroSD slot
(CLK=GPIO 38, CMD=GPIO 40, D0=GPIO 39) with fallback to standard SPI and SDMMC.
"""

import os
import sys

def remap_s3_sdmmc_freenove():
    """Remaps ESP32-S3 hardware SDMMC peripheral signals to Freenove onboard pins."""
    try:
        import machine
        # 1. Initialize pins to establish proper IO_MUX input/output configuration
        _ = machine.Pin(38, machine.Pin.OUT)
        _ = machine.Pin(40, machine.Pin.OUT)
        _ = machine.Pin(39, machine.Pin.IN, machine.Pin.PULL_UP)

        # 2. Output signals routing (GPIO_FUNCx_OUT_SEL_CFG_REG: 0x60004554 + 4*pin)
        # Signal 173 = SDMMC_CLK -> GPIO 38
        machine.mem32[0x60004554 + 4 * 38] = 173
        # Signal 179 = SDMMC_CMD_OUT -> GPIO 40
        machine.mem32[0x60004554 + 4 * 40] = 179
        # Signal 213 = SDMMC_D0_OUT -> GPIO 39
        machine.mem32[0x60004554 + 4 * 39] = 213

        # 3. Input signals routing (GPIO_FUNCy_IN_SEL_CFG_REG: 0x60004154 + 4*y)
        # Signal 179 = SDMMC_CMD_IN (reg 0x60004420) <- GPIO 40
        machine.mem32[0x60004420] = 0x80 | 40
        # Signal 213 = SDMMC_D0_IN (reg 0x600044A8) <- GPIO 39
        machine.mem32[0x600044A8] = 0x80 | 39

        # 4. Disconnect SDMMC signals from default reference pins (14, 15, 2)
        machine.mem32[0x60004554 + 4 * 14] = 0x100
        machine.mem32[0x60004554 + 4 * 15] = 0x100
        machine.mem32[0x60004554 + 4 * 2]  = 0x100
        return True
    except Exception as e:
        print(f"  [Matrix Remap Warning] {e}")
        return False


def probe_sdcard():
    try:
        import machine
    except ImportError:
        print("[Error] This script must run on a MicroPython board.")
        return

    print("=" * 60)
    print("  ESP32 SD Card Hardware Detector & Validator")
    print("=" * 60)
    print(f"Platform: {sys.platform}")

    mount_path = "/sd"

    # Clean unmount if previously mounted
    try:
        os.umount(mount_path)
    except Exception:
        pass

    sd = None
    strategy_used = None

    # Strategy 1: Freenove ESP32-S3 SDMMC with Dynamic GPIO Matrix Remap (CLK=38, CMD=40, D0=39)
    print("\n[1/3] Testing Freenove SDMMC 1-line mode (CLK=38, CMD=40, D0=39)...")
    try:
        remap_s3_sdmmc_freenove()
        sd = machine.SDCard(slot=1, width=1)
        # Verify the remap is held after controller initialization
        remap_s3_sdmmc_freenove()
        os.mount(sd, mount_path)
        strategy_used = "Freenove Hardware SDMMC (1-line, GPIO 38/40/39)"
        print("  -> Mounted successfully via Hardware SDMMC!")
    except Exception as e:
        print(f"  -> SDMMC attempt result: {type(e).__name__}: {e}")
        sd = None
        try:
            os.umount(mount_path)
        except Exception:
            pass

    # Strategy 2: SPI Mode on Freenove Onboard Pins (SCK=38, MOSI=40, MISO=39, CS=47)
    if sd is None:
        print("\n[2/3] Testing SPI Slot 2 on Freenove pins (SCK=38, MOSI=40, MISO=39, CS=47)...")
        try:
            sd = machine.SDCard(slot=2, sck=machine.Pin(38), mosi=machine.Pin(40), miso=machine.Pin(39), cs=machine.Pin(47))
            os.mount(sd, mount_path)
            strategy_used = "SPI Slot 2 (SCK=38, MOSI=40, MISO=39, CS=47)"
            print("  -> Mounted successfully via SPI Slot 2!")
        except Exception as e:
            print(f"  -> SPI attempt result: {type(e).__name__}: {e}")
            sd = None
            try:
                os.umount(mount_path)
            except Exception:
                pass

    # Strategy 3: Standard Default SDMMC Slot 1
    if sd is None:
        print("\n[3/3] Testing default machine.SDCard(slot=1)...")
        try:
            sd = machine.SDCard(slot=1, width=1)
            os.mount(sd, mount_path)
            strategy_used = "Standard SDMMC Slot 1"
            print("  -> Mounted successfully via default SDMMC slot 1!")
        except Exception as e:
            print(f"  -> Default SDMMC result: {type(e).__name__}: {e}")
            sd = None

    if sd is None:
        print("\n" + "!" * 60)
        print("  FAILED TO MOUNT SD CARD")
        print("!" * 60)
        print("  Possible causes:")
        print("  1. The card is not formatted as FAT32 (MicroPython does NOT support exFAT or NTFS).")
        print("  2. The card is not clicked firmly all the way into the spring socket.")
        print("  3. Partition table is not MBR (Master Boot Record).")
        print("!" * 60)
        return

    # Benchmark and report filesystem metrics
    try:
        stat = os.statvfs(mount_path)
        bsize = stat[0]
        total_blocks = stat[2]
        free_blocks = stat[3]
        total_mb = (bsize * total_blocks) / (1024 * 1024)
        free_mb = (bsize * free_blocks) / (1024 * 1024)
        used_mb = max(0, total_mb - free_mb)
        pct_used = (used_mb / total_mb) * 100 if total_mb else 0
        total_gb = total_mb / 1024
        free_gb = free_mb / 1024

        print("\n" + "=" * 60)
        print("  SUCCESS: SD CARD DETECTED AND MOUNTED!")
        print("=" * 60)
        print(f"  Connection Mode: {strategy_used}")
        print(f"  Mount Point:     {mount_path}")
        print(f"  Total Capacity:  {total_gb:.2f} GB ({total_mb:.1f} MB)")
        print(f"  Used Space:      {used_mb:.1f} MB ({pct_used:.1f}%)")
        print(f"  Free Space:      {free_gb:.2f} GB ({free_mb:.1f} MB)")
        print(f"  Files in root:   {os.listdir(mount_path)}")

        # Write & Read verification test
        test_file = f"{mount_path}/.espmui_test.tmp"
        test_payload = "espmui SD Card verification: PASSED\n"
        with open(test_file, "w") as f:
            f.write(test_payload)
        with open(test_file) as f:
            read_back = f.read()
        os.remove(test_file)

        if read_back == test_payload:
            print("  Read/Write Test: PASSED (Verified data integrity)")
        else:
            print("  Read/Write Test: FAILED (Readback mismatch)")
        print("=" * 60)
    except Exception as e:
        print(f"  Error reading filesystem stats: {e}")


if __name__ == "__main__":
    probe_sdcard()
