import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import pandas as pd

# [추가] 하단 'Created by'와 메뉴 숨기기 (모바일 깔끔하게)
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# 1. 페이지 설정
st.set_page_config(page_title="헤나세르 AI 스타일러", layout="centered")
st.title("✂️ 헤나세르 AI 가상 스타일링 (MVP)")

# 2. 인증 설정
try:
    # Google Sheets 인증
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gspread_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    
    # 시트 열기
    sh = client.open_by_url(st.secrets["gsheets_url"])
    worksheet = sh.get_worksheet(0) # 첫 번째 탭
except Exception as e:
    st.error(f"설정 오류가 발생했습니다: {e}")
    st.stop()

# 제미나이 설정
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('nano-banana-pro-preview')

# 3. 메인 로직
with st.sidebar:
    st.header("🔑 멤버십 인증")
    access_key = st.text_input("액세스 키를 입력하세요", type="password")

if access_key:
    # 실시간 시트 데이터 확인
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    user_row = df[df['Access_Key'].astype(str) == access_key]

    if not user_row.empty:
        idx = user_row.index[0] # 시트에서의 행 위치
        remaining = int(user_row.iloc[0]['Remaining_Count'])
        
        if remaining > 0:
            st.success(f"✅ 인증 성공! 잔여 횟수: {remaining}회")
            
            mode = st.selectbox("어떤 스타일을 시뮬레이션할까요?", ["헤어", "아우터", "이너"])
            
            col1, col2 = st.columns(2)
            st.markdown("### 👤 <span style='font-size: 24px;'>내 정면 사진 (Base)</span>", unsafe_allow_html=True)
            with col1:
                base_img = st.file_uploader("본인의 정면 사진", type=['jpg', 'png', 'jpeg'])
            st.markdown("---")
            st.markdown("### 💇‍♂️ <span style='font-size: 24px;'>참고할 헤어 사진 (Style)</span>", unsafe_allow_html=True)

            # 3. 예시 이미지 및 문구 추가
            st.info("💡 아래와 같은 '정면'을 준비해주세요. (측면 사진은 불가해요)")
            # 예시 이미지가 폴더에 있다면 경로 입력, 없다면 주석 처리하세요.
            st.image("example_front.jpg", width=200)
            with col2:
                style_img = st.file_uploader("원하는 헤어 스타일 사진", type=['jpg', 'png', 'jpeg'])

            if base_img and style_img:
                if st.button(f"✨ {mode} 합성 시작하기 (1~2분)"):
                    with st.spinner("1~2분 정도 소요됩니다. 페이지를 이탈하지 마세요."):
                        img_a = Image.open(base_img)
                        img_b = Image.open(style_img)
                        
                        # 헤나세르님이 제안하신 프롬프트를 시스템 명령어로 구성
                        # 첫 번째 인자가 Image A, 두 번째 인자가 Image B임을 명시합니다.
                        prompt = f"""
                        You are given two images in sequence. 
                        The FIRST image is Image A (BASE_IMAGE), and the SECOND image is Image B (STYLE_IMAGE).

                        [Image A (BASE_IMAGE)]: This is the customer's original photo. 
                        - Do not change the person's face, identity, skin tone, facial features, or eyebrows.

                        [Image B (STYLE_IMAGE)]: This image is provided ONLY as a {mode} reference.

                        [Task]:
                        - Replace ONLY the {mode} of the person in Image A.
                        - Use the {mode} from Image B as a reference for the new look.
                        - Keep the face, eyebrows, eyes, nose, mouth, and facial proportions of Image A exactly the same.
                        - Do not modify clothing, body, background, or lighting.

                        [Important Rules]:
                        - The final output must look like the EXACT SAME person from Image A.
                        - Only the {mode} should be changed naturally.
                        - Output ONLY the resulting image file.
                        """
                        
                        try:
                            # 순서가 매우 중요합니다: [프롬프트, 베이스이미지(A), 스타일이미지(B)]
                            response = model.generate_content([prompt, img_a, img_b])
                            
                            found_image = False
                            if response.candidates:
                                for part in response.candidates[0].content.parts:
                                    if part.inline_data:
                                        st.image(part.inline_data.data, caption="✨ 헤나세르 AI 시뮬레이션 완료")
                                        found_image = True
                            
                            if found_image:
                                # 합성이 성공했을 때만 횟수 차감 및 축하 효과
                                worksheet.update_cell(idx + 2, 3, remaining - 1)
                                st.balloons()
                                st.success(f"스타일링 완료! 잔여 횟수: {remaining - 1}회")
                            else:
                                st.error("AI가 이미지를 생성하지 못했습니다. 프롬프트나 이미지 정책을 확인해주세요.")
                                if hasattr(response, 'text'): st.write(response.text)

                        except Exception as e:
                            st.error(f"합성 엔진 오류: {e}")
        else:
            st.error("잔여 횟수가 0입니다. 충전이 필요합니다.")
    else:
        st.error("잘못된 키입니다.")
else:
    st.info("좌측 상단의 '>>'를 눌러서 키를 입력해주세요.")