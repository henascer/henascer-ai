import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image
import pandas as pd
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import io

# 모델 선언 부분
model = genai.GenerativeModel(
    'nano-banana-pro-preview',
    safety_settings={
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
)


# 1. 페이지 설정
st.set_page_config(page_title="헤나세르 AI 스타일러", layout="centered")
st.title("✂️ 헤나세르 AI 가상 스타일링 (MVP)")

# 하단 푸터 및 메뉴 숨기기 CSS
hide_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            </style>
            """
st.markdown(hide_style, unsafe_allow_html=True)

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
    access_key = st.text_input("액세스 키를 입력하세요 (대소문자 구분)", type="password")

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
            
            # 1. 스타일 선택
            mode = st.selectbox("어떤 스타일을 시뮬레이션할까요?", ["헤어", "아우터", "이너"])
            
            st.markdown("---")

            # 2. 내 정면 사진 (Base) 섹션
            st.markdown("### 👤 <span style='font-size: 24px;'>내 정면 사진 (Base)</span>", unsafe_allow_html=True)
            # label_visibility="collapsed"를 추가하면 내부의 "본인의 정면 사진" 글자가 사라집니다.
            base_img = st.file_uploader("본인의 정면 사진", type=['jpg', 'png', 'jpeg'], label_visibility="collapsed")
            
            st.markdown("---")

            # 3. 합성할 헤어 사진 (Style) 섹션
            st.markdown("### 💇‍♂️ <span style='font-size: 24px;'>합성할 헤어 사진 (Style)</span>", unsafe_allow_html=True)
            
            # 안내 문구 및 예시 이미지
            st.info("💡 아래와 같은 '정면' 예시를 준비해주세요. (측면 사진은 불가해요)")
            st.image("example_front.jpg", width=250, caption="[합성이 잘 되는 정면 예시]")
            
            # 헤어 사진 업로드 창
            style_img = st.file_uploader("원하는 헤어 스타일 사진", type=['jpg', 'png', 'jpeg'], label_visibility="collapsed")

            st.markdown("---")

            # 4. 실행 버튼
            if base_img and style_img:
                if st.button(f"✨ {mode} 합성 시작하기 (1~2분)"):
                    with st.spinner("1~2분 정도 소요됩니다. 페이지를 이탈하거나 새로고침 하지 마세요."):
                        # 이미지 처리 및 합성 로직 시작
                        img_a = Image.open(base_img)
                        img_b = Image.open(style_img)
                                                
                        # 헤나세르님이 제안하신 프롬프트를 시스템 명령어로 구성
                        # 첫 번째 인자가 Image A, 두 번째 인자가 Image B임을 명시합니다.
                        prompt = f"""
                        URGENT: Strict head pose alignment. The nose and eyes in the output MUST be in the exact same pixel coordinates as Image A.
                        
                        [Role]: You are a Master AI Stylist specializing in photo-realistic Virtual Try-on.

                        [Input]:
                        - Image 1 (The FIRST image): BASE_IMAGE (The customer)
                        - Image 2 (The SECOND image): STYLE_IMAGE (The reference look)

                        [PRIME DIRECTIVE - CRITICAL]:
                        1. TARGET RECOGNITION: Focus ONLY on the human subject's head and body. Strictly ignore all mobile UI elements (status bars, notches, buttons, white/black bars) in both images.
                        2. IDENTITY ANCHOR: Use Image 1 as the absolute anchor. Do NOT rotate, tilt, or distort the face. The eye-line, nose position, and head angle must be 100% identical to Image 1.
                        3. STYLE EXTRACTION: Extract only the {mode} (texture, color, silhouette) from Image 2.

                        [Task]:
                        - "Surgically" replace ONLY the {mode} of the person in Image 1 with the style from Image 2.
                        - Head Pose Alignment: Ensure the new {mode} is naturally fitted onto the original head position of Image 1.
                        - Seamless Blending: The hairline and the area where the skin meets the {mode} must be perfectly blended with realistic shadows.
                        - Preservation: Keep the original facial features (eyebrows, eyes, skin texture), background, and clothing of Image 1 untouched.

                        [Important Rules]:
                        - The result must be a SINGLE integrated photo, NOT a side-by-side comparison.
                        - The person's identity and facial proportions must remain 100% recognizable as the person in Image 1.
                        - No text, no descriptions, no watermarks. Output ONLY the resulting image.
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
                                st.success(f"스타일링 완료! 잔여 횟수: {remaining - 1}회")
                                # 이미지 데이터를 바이너리로 변환하여 다운로드 버튼 생성
                                buf = io.BytesIO()
                                # part.inline_data.data는 바이너리 데이터이므로 그대로 활용 가능합니다.
                                st.download_button(
                                    label="💾 결과 이미지 저장하기",
                                    data=part.inline_data.data,
                                    file_name="henascer_style_result.png",
                                    mime="image/png"
                                )
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
    st.info("좌측 상단의 ' >> '를 눌러서 키를 입력해주세요.")