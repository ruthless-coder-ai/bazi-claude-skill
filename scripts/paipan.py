#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""八字排盘脚本：输入出生信息，输出完整排盘 JSON。

用法示例:
  python3 paipan.py --date 1990-03-15 --time 14:30 --gender 女 --longitude 116.4
  python3 paipan.py --date 1990-02-19 --lunar --gender 男            # 农历输入
  python3 paipan.py --date 1990-03-15 --gender 女                    # 不知时辰(排三柱)

参数:
  --date        出生日期 YYYY-MM-DD (公历; 加 --lunar 则视为农历)
  --time        出生时间 HH:MM (省略 = 时辰未知, 只排年月日三柱)
  --gender      男/女 (排大运必需)
  --lunar       日期为农历
  --leap        农历闰月
  --longitude   出生地经度(东经为正), 提供则做真太阳时校正
  --tz-meridian 出生时钟表所用时区的标准经度, 默认 120 (北京时间UTC+8)。
                欧洲冬令时 UTC+1 → 15, 夏令时 UTC+2 → 30, 以此类推。
  --sect        晚子时流派: 2=23点后日柱算当天(默认), 1=算次日
"""
import argparse
import json
import math
import sys
from datetime import datetime, timedelta

try:
    from lunar_python import Solar, Lunar
except ImportError:
    print(json.dumps({"error": "缺少依赖库, 请先运行: pip install lunar-python"},
                     ensure_ascii=False))
    sys.exit(1)

GAN_WUXING = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土",
              "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水"}
GAN_YINYANG = {"甲": "阳", "乙": "阴", "丙": "阳", "丁": "阴", "戊": "阳",
               "己": "阴", "庚": "阳", "辛": "阴", "壬": "阳", "癸": "阴"}
ZHI_WUXING = {"子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
              "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}
ZHI_SHICHEN = {"子": "23:00-01:00", "丑": "01:00-03:00", "寅": "03:00-05:00",
               "卯": "05:00-07:00", "辰": "07:00-09:00", "巳": "09:00-11:00",
               "午": "11:00-13:00", "未": "13:00-15:00", "申": "15:00-17:00",
               "酉": "17:00-19:00", "戌": "19:00-21:00", "亥": "21:00-23:00"}

# 十神: 以日干为"我", 按五行生克 + 阴阳同异
_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}  # 我生
_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}      # 我克


def shi_shen(day_gan, other_gan):
    me, other = GAN_WUXING[day_gan], GAN_WUXING[other_gan]
    same = GAN_YINYANG[day_gan] == GAN_YINYANG[other_gan]
    if other == me:
        return "比肩" if same else "劫财"
    if _SHENG[me] == other:
        return "食神" if same else "伤官"
    if _KE[me] == other:
        return "偏财" if same else "正财"
    if _KE[other] == me:
        return "七杀" if same else "正官"
    return "偏印" if same else "正印"


# ---- 常用神煞 ----
_TIANYI = {"甲": "丑未", "戊": "丑未", "庚": "丑未", "乙": "子申", "己": "子申",
           "丙": "亥酉", "丁": "亥酉", "壬": "卯巳", "癸": "卯巳", "辛": "午寅"}
_SANHE_GROUP = {z: g for g, zs in
                {"申子辰": "申子辰", "寅午戌": "寅午戌", "巳酉丑": "巳酉丑", "亥卯未": "亥卯未"}.items()
                for z in zs}
_TAOHUA = {"申子辰": "酉", "寅午戌": "卯", "巳酉丑": "午", "亥卯未": "子"}
_YIMA = {"申子辰": "寅", "寅午戌": "申", "巳酉丑": "亥", "亥卯未": "巳"}
_HUAGAI = {"申子辰": "辰", "寅午戌": "戌", "巳酉丑": "丑", "亥卯未": "未"}
_YANGREN = {"甲": "卯", "丙": "午", "戊": "午", "庚": "酉", "壬": "子"}
_WENCHANG = {"甲": "巳", "乙": "午", "丙": "申", "戊": "申", "丁": "酉",
             "己": "酉", "庚": "亥", "辛": "子", "壬": "寅", "癸": "卯"}


def shen_sha(day_gan, year_zhi, day_zhi, all_zhi, pillar_names):
    """返回命中出现的常用神煞及落在哪一柱。all_zhi 与 pillar_names 一一对应。"""
    found = []

    def hit(target_zhis, name, note):
        for z, pos in zip(all_zhi, pillar_names):
            if z in target_zhis:
                found.append({"神煞": name, "落点": f"{pos}({z})", "说明": note})

    hit(_TIANYI.get(day_gan, ""), "天乙贵人", "逢凶化吉、易得贵人相助")
    for base, base_name in ((year_zhi, "年支"), (day_zhi, "日支")):
        g = _SANHE_GROUP.get(base)
        if not g:
            continue
        for table, name, note in ((_TAOHUA, "桃花", "人缘异性缘佳"),
                                  (_YIMA, "驿马", "奔波走动、迁移变动"),
                                  (_HUAGAI, "华盖", "才艺孤高、喜哲思玄学")):
            for z, pos in zip(all_zhi, pillar_names):
                if z == table[g]:
                    entry = {"神煞": name, "落点": f"{pos}({z})", "说明": note + f"（以{base_name}起）"}
                    if entry not in found:
                        found.append(entry)
    if day_gan in _YANGREN:
        hit(_YANGREN[day_gan], "羊刃", "性刚烈、行动力强, 忌冲")
    if day_gan in _WENCHANG:
        hit(_WENCHANG[day_gan], "文昌", "聪慧好学、利考试文书")
    return found


def equation_of_time(day_of_year):
    """均时差近似(分钟)。"""
    b = 2 * math.pi * (day_of_year - 81) / 364.0
    return 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)


def pillar_info(gan_zhi, day_gan, hide_gan, shishen_gan, shishen_zhi, na_yin):
    gan, zhi = gan_zhi[0], gan_zhi[1]
    return {
        "干支": gan_zhi,
        "天干": {"字": gan, "五行": f"{GAN_YINYANG[gan]}{GAN_WUXING[gan]}", "十神": shishen_gan},
        "地支": {"字": zhi, "五行": ZHI_WUXING[zhi],
                 "藏干": [{"字": g, "五行": GAN_WUXING[g],
                           "十神": s} for g, s in zip(hide_gan, shishen_zhi)]},
        "纳音": na_yin,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--time", default=None)
    p.add_argument("--gender", default=None)
    p.add_argument("--lunar", action="store_true")
    p.add_argument("--leap", action="store_true")
    p.add_argument("--longitude", type=float, default=None)
    p.add_argument("--tz-meridian", type=float, default=120.0)
    p.add_argument("--sect", type=int, default=2, choices=(1, 2))
    args = p.parse_args()

    y, m, d = (int(x) for x in args.date.split("-"))
    time_known = args.time is not None
    if time_known:
        hh, mm = (int(x) for x in args.time.split(":"))
    else:
        hh, mm = 12, 0  # 占位, 时柱不输出

    warnings = []

    # 农历转公历
    if args.lunar:
        lm = -m if args.leap else m
        lunar_in = Lunar.fromYmdHms(y, lm, d, hh, mm, 0)
        solar = lunar_in.getSolar()
        warnings.append(f"输入为农历 {y}年{'闰' if args.leap else ''}{m}月{d}日, "
                        f"转换为公历 {solar.toYmd()}")
        y, m, d = solar.getYear(), solar.getMonth(), solar.getDay()

    clock_dt = datetime(y, m, d, hh, mm)
    used_dt = clock_dt

    # 真太阳时校正
    solar_time_info = None
    if args.longitude is not None and time_known:
        lon_min = (args.longitude - args.tz_meridian) * 4.0
        eot_min = equation_of_time(clock_dt.timetuple().tm_yday)
        offset = lon_min + eot_min
        used_dt = clock_dt + timedelta(minutes=offset)
        solar_time_info = {
            "钟表时间": clock_dt.strftime("%Y-%m-%d %H:%M"),
            "经度校正_分钟": round(lon_min, 1),
            "均时差_分钟": round(eot_min, 1),
            "真太阳时": used_dt.strftime("%Y-%m-%d %H:%M"),
        }
        if used_dt.date() != clock_dt.date():
            warnings.append("真太阳时校正后跨日, 日柱可能与钟表日期不同, 已按校正后时间排盘")

    # 时辰边界预警: 时辰在奇数点切换 (1,3,...,23)
    if time_known:
        minutes = used_dt.hour * 60 + used_dt.minute
        for boundary_h in range(1, 25, 2):
            diff = abs(minutes - boundary_h * 60)
            diff = min(diff, 1440 - diff)
            if diff <= 15:
                warnings.append(
                    f"出生时间距时辰边界({boundary_h % 24}:00)仅约{diff}分钟, "
                    "时柱存在两可, 建议同时参考相邻时辰的盘")
                break
        if 23 <= used_dt.hour or used_dt.hour < 1:
            warnings.append(f"出生于子时(23:00-01:00), 采用{'晚子时日柱算当天' if args.sect == 2 else '晚子时日柱算次日'}的流派(sect={args.sect}), 另一流派日柱会不同")

    solar_obj = Solar.fromYmdHms(used_dt.year, used_dt.month, used_dt.day,
                                 used_dt.hour, used_dt.minute, 0)
    lunar = solar_obj.getLunar()
    ec = lunar.getEightChar()
    ec.setSect(args.sect)

    day_gan = ec.getDayGan()

    # 节气边界预警(年柱看立春, 月柱看节)
    prev_jie, next_jie = lunar.getPrevJie(), lunar.getNextJie()
    for jq, label in ((prev_jie, "上一个节"), (next_jie, "下一个节")):
        jd = jq.getSolar()
        jq_dt = datetime(jd.getYear(), jd.getMonth(), jd.getDay(),
                         jd.getHour(), jd.getMinute())
        gap_h = abs((used_dt - jq_dt).total_seconds()) / 3600
        if gap_h <= 48:
            warnings.append(
                f"出生时间距节气「{jq.getName()}」({jq_dt.strftime('%Y-%m-%d %H:%M')})"
                f"约{gap_h:.0f}小时, {'年柱和' if jq.getName() == '立春' else ''}月柱切换临界, 请核对出生时间准确性")

    pillars = {
        "年柱": pillar_info(ec.getYear(), day_gan, ec.getYearHideGan(),
                            ec.getYearShiShenGan(), ec.getYearShiShenZhi(), ec.getYearNaYin()),
        "月柱": pillar_info(ec.getMonth(), day_gan, ec.getMonthHideGan(),
                            ec.getMonthShiShenGan(), ec.getMonthShiShenZhi(), ec.getMonthNaYin()),
        "日柱": pillar_info(ec.getDay(), day_gan, ec.getDayHideGan(),
                            "日主", ec.getDayShiShenZhi(), ec.getDayNaYin()),
    }
    if time_known:
        pillars["时柱"] = pillar_info(ec.getTime(), day_gan, ec.getTimeHideGan(),
                                      ec.getTimeShiShenGan(), ec.getTimeShiShenZhi(),
                                      ec.getTimeNaYin())
    else:
        warnings.append("时辰未知, 仅排年月日三柱; 时柱相关(子女宫/晚年运细节)无法精确判断")

    # 五行统计(天干+地支本气, 藏干单列)
    chars = []
    for name, pi in pillars.items():
        chars.append(GAN_WUXING[pi["干支"][0]])
        chars.append(ZHI_WUXING[pi["干支"][1]])
    wuxing_count = {wx: chars.count(wx) for wx in ("木", "火", "土", "金", "水")}

    all_zhi = [pi["干支"][1] for pi in pillars.values()]
    pillar_names = list(pillars.keys())

    result = {
        "输入": {
            "公历生日": f"{y}-{m:02d}-{d:02d}",
            "出生时间": args.time if time_known else "未知",
            "性别": args.gender or "未提供",
            "农历": f"{lunar.getYearInChinese()}年{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}",
            "生肖": lunar.getYearShengXiao(),
        },
        "真太阳时": solar_time_info,
        "四柱": pillars,
        "日主": {"天干": day_gan, "五行": f"{GAN_YINYANG[day_gan]}{GAN_WUXING[day_gan]}"},
        "五行统计_不含藏干": wuxing_count,
        "月令": ec.getMonth()[1],
        "空亡_日柱旬空": ec.getDayXunKong(),
        "神煞": shen_sha(day_gan, pillars["年柱"]["干支"][1], pillars["日柱"]["干支"][1],
                         all_zhi, pillar_names),
        "提醒": warnings,
    }

    # 大运/流年/流月 (需性别)
    gender = (args.gender or "").strip()
    if gender in ("男", "male", "m", "M", "1"):
        gender_code = 1
    elif gender in ("女", "female", "f", "F", "0"):
        gender_code = 0
    else:
        gender_code = None
        result["提醒"].append("未提供性别, 无法排大运流年(大运顺逆取决于年干阴阳+性别)")

    if gender_code is not None:
        yun = ec.getYun(gender_code)
        start_solar = yun.getStartSolar()
        da_yun_list = []
        now = datetime.now()
        current_dayun = None
        for dy in yun.getDaYun():
            gz = dy.getGanZhi()
            entry = {
                "干支": gz if gz else "(起运前)",
                "虚岁": f"{dy.getStartAge()}-{dy.getEndAge()}",
                "公历": f"{dy.getStartYear()}-{dy.getEndYear()}",
            }
            if gz:
                entry["天干十神"] = shi_shen(day_gan, gz[0])
                entry["地支五行"] = ZHI_WUXING[gz[1]]
            da_yun_list.append(entry)
            if dy.getStartYear() <= now.year <= dy.getEndYear():
                current_dayun = dy
        result["大运"] = {
            "起运": f"出生后{yun.getStartYear()}年{yun.getStartMonth()}个月{yun.getStartDay()}天, "
                    f"公历{start_solar.toYmd()}起运",
            "方向": "顺行" if yun.isForward() else "逆行",
            "各步大运": da_yun_list,
        }

        if current_dayun is not None:
            cur = {"当前大运": current_dayun.getGanZhi() or "(起运前)",
                   "大运区间": f"{current_dayun.getStartYear()}-{current_dayun.getEndYear()}"}
            liu_nian_out = []
            for ln in current_dayun.getLiuNian():
                if now.year - 1 <= ln.getYear() <= now.year + 3:
                    item = {"年份": ln.getYear(), "干支": ln.getGanZhi(),
                            "虚岁": ln.getAge(),
                            "天干十神": shi_shen(day_gan, ln.getGanZhi()[0])}
                    if ln.getYear() == now.year:
                        item["流月"] = [
                            {"月": lm.getMonthInChinese(), "干支": lm.getGanZhi(),
                             "天干十神": shi_shen(day_gan, lm.getGanZhi()[0])}
                            for lm in ln.getLiuYue()]
                    liu_nian_out.append(item)
            cur["流年_去年至未来三年"] = liu_nian_out
            result["当前运势"] = cur

    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
