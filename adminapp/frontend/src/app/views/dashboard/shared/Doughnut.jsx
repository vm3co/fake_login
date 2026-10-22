import { useContext } from "react";
import ReactEcharts from "echarts-for-react";
import { useTheme } from "@mui/material/styles";
import Box from "@mui/material/Box";
import { Paragraph } from "app/components/Typography";

import { SendtaskListContext } from "app/contexts/SendtaskListContext";


export default function DoughnutChart({ height, color = [] }) {
  const theme = useTheme();
  const { loading, statsData, todayTasks } = useContext(SendtaskListContext);

  const totals = todayTasks.reduce(
    (acc, row) => {
      const stats = statsData[row.sendtask_uuid] || {};
      acc.todayunsend += Number(stats.todayunsend) || 0;
      acc.todaysuccess += Number(stats.todaysuccess) || 0;
      acc.todayfailed += (Number(stats.todaysend) || 0) - (Number(stats.todaysuccess) || 0);
      return acc;
    },
    { todayunsend: 0, todaysuccess: 0, todayfailed: 0 }
  );

  const option = {
    legend: {
      orient: "vertical",       // 垂直排列 legend 項目
      left: 0,                  // 靠左側顯示（你也可以寫 "left: '5%'" 調整間距）
      top: "center",            // 垂直置中      
      // bottom: 0,
      show: true,
      itemGap: 20,
      icon: "circle",
      textStyle: { color: theme.palette.text.secondary, fontSize: 13, fontFamily: "roboto" }
    },
    tooltip: { show: false, trigger: "item", formatter: "{a} <br/>{b}: {c} ({d}%)" },
    xAxis: [{ axisLine: { show: false }, splitLine: { show: false } }],
    yAxis: [{ axisLine: { show: false }, splitLine: { show: false } }],

    series: [
      {
        name: "Traffic Rate",
        type: "pie",
        hoverOffset: 5,
        radius: ["60%", "90%"],
        center: ["65%", "50%"],
        avoidLabelOverlap: false,
        stillShowZeroSum: false,
        labelLine: { show: false },
        label: {
          show: false,
          fontSize: 13,
          formatter: "{a}",
          position: "center",
          fontFamily: "roboto",
          color: theme.palette.text.secondary
        },
        emphasis: {
          label: {
            show: true,
            fontSize: "14",
            padding: 4,
            fontWeight: "normal",
            formatter: "{b} \n{c} ({d}%)"
            // formatter: "{b} ({d}%)"
          },
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: "rgba(0, 0, 0, 0.5)"
          }
        },
        data: [
          { value: totals.todayunsend, name: "預計寄出" },
          { value: totals.todaysuccess, name: "寄出成功" },
          { value: totals.todayfailed, name: "寄出失敗" }
        ]
      }
    ]
  };

  if (loading)
    return (
      <Box display="flex" alignItems="center" justifyContent="center" minHeight="300px">
        <Paragraph>載入中...</Paragraph>
      </Box>
    );


  return <ReactEcharts style={{ height }} option={{ ...option, color: [...color] }} />;
}
